"""SQLite data-access layer — thin, typed helpers over the schema.

A single shared connection guarded by a lock. The dashboard serves one
operator at low concurrency, so this is simple and entirely sufficient;
queries are sub-millisecond.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

Row = dict[str, Any]


class Database:
    def __init__(self, path: Path | str, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        self._lock = threading.Lock()
        if read_only:
            # Root-run tools open the database read-only so they never create
            # root-owned WAL files that the unprivileged dashboard cannot write.
            try:
                self._conn = sqlite3.connect(f"file:{self.path}?mode=ro",
                                             uri=True, check_same_thread=False)
            except sqlite3.OperationalError:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if not read_only:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ low level
    def executescript(self, sql: str) -> None:
        with self._lock:
            self._conn.executescript(sql)
            self._conn.commit()

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[Row]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[Row]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur.lastrowid or 0

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(s) for s in seq])
            self._conn.commit()

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        try:
            row = self.query_one("SELECT value FROM settings WHERE key=?", (key,))
        except sqlite3.OperationalError:
            return default          # database not yet initialised
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=datetime('now')",
            (key, value))

    def get_json(self, key: str, default: Any = None) -> Any:
        raw = self.get_setting(key)
        try:
            return json.loads(raw) if raw is not None else default
        except json.JSONDecodeError:
            return default

    def set_json(self, key: str, value: Any) -> None:
        self.set_setting(key, json.dumps(value, separators=(",", ":")))

    def all_settings(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self.query("SELECT key,value FROM settings")}

    # ------------------------------------------------------------------ events
    def log_event(self, category: str, message: str,
                  level: str = "info", detail: Optional[str] = None) -> None:
        self.execute(
            "INSERT INTO events(level,category,message,detail) VALUES(?,?,?,?)",
            (level, category, message, detail))

    def recent_events(self, limit: int = 100,
                      category: Optional[str] = None) -> list[Row]:
        limit = max(1, min(limit, 1000))
        if category:
            return self.query(
                "SELECT * FROM events WHERE category=? ORDER BY id DESC LIMIT ?",
                (category, limit))
        return self.query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    def prune_events(self, keep: int = 5000) -> None:
        self.execute(
            "DELETE FROM events WHERE id NOT IN "
            "(SELECT id FROM events ORDER BY id DESC LIMIT ?)", (keep,))

    # ------------------------------------------------------------------ devices
    def list_devices(self, guest: Optional[bool] = None) -> list[Row]:
        if guest is None:
            return self.query("SELECT * FROM devices ORDER BY last_seen DESC")
        return self.query(
            "SELECT * FROM devices WHERE is_guest=? ORDER BY last_seen DESC",
            (1 if guest else 0,))

    def get_device(self, mac: str) -> Optional[Row]:
        return self.query_one("SELECT * FROM devices WHERE mac=?", (mac,))

    def count_devices(self) -> int:
        row = self.query_one("SELECT COUNT(*) AS n FROM devices")
        return int(row["n"]) if row else 0

    def upsert_device(self, mac: str, **fields: Any) -> None:
        existing = self.get_device(mac)
        if existing:
            if fields:
                cols = ", ".join(f"{k}=?" for k in fields)
                self.execute(
                    f"UPDATE devices SET {cols}, last_seen=datetime('now') WHERE mac=?",
                    (*fields.values(), mac))
            else:
                self.execute(
                    "UPDATE devices SET last_seen=datetime('now') WHERE mac=?", (mac,))
        else:
            cols = ["mac"] + list(fields.keys())
            placeholders = ", ".join("?" for _ in cols)
            self.execute(
                f"INSERT INTO devices({', '.join(cols)}) VALUES({placeholders})",
                (mac, *fields.values()))

    def delete_device(self, mac: str) -> None:
        self.execute("DELETE FROM devices WHERE mac=?", (mac,))

    # ------------------------------------------------------------------ sessions
    def create_session(self, token: str, expires_at: str,
                       user_agent: str = "", ip: str = "") -> None:
        self.execute(
            "INSERT INTO sessions(token,expires_at,user_agent,ip) VALUES(?,?,?,?)",
            (token, expires_at, user_agent, ip))

    def get_session(self, token: str) -> Optional[Row]:
        if not token:
            return None
        return self.query_one(
            "SELECT * FROM sessions WHERE token=? AND expires_at > datetime('now')",
            (token,))

    def delete_session(self, token: str) -> None:
        self.execute("DELETE FROM sessions WHERE token=?", (token,))

    def purge_expired_sessions(self) -> None:
        self.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
