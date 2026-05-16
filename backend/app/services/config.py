"""System config file backup helper.

Every routine that edits a system file (hostapd, dnsmasq, netplan, nftables,
NetworkManager) calls backup_paths first, so a known-good copy always exists
and is recorded in the database for the recovery tooling.
"""
from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path

from ..core.settings import settings
from ..db.repo import Database


def backup_paths(db: Database, category: str, paths: list[str],
                 note: str = "") -> str | None:
    """Archive the given existing paths into a timestamped tarball.

    Returns the archive path, or None if none of the paths exist.
    """
    existing = [Path(p) for p in paths if Path(p).exists()]
    if not existing:
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    archive = settings.backup_dir / f"{category}-{ts}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in existing:
            tar.add(path, arcname=str(path).lstrip("/"))
    db.execute("INSERT INTO config_backups(category,path,note) VALUES(?,?,?)",
               (category, str(archive), note))
    db.log_event("system", f"Backed up {category} config", detail=str(archive))
    return str(archive)


def list_backups(db: Database, limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM config_backups ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 200)),))
