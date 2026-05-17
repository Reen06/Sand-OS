"""Application settings, loaded from the environment with safe defaults.

Values come from /etc/sandos/sandos.env (installed from
config/sandos.env) via the systemd unit's EnvironmentFile. During
development the same variables can be exported manually.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # .../sandos


def _env(key: str, default: str) -> str:
    value = os.environ.get(key, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    home: Path
    db_path: Path
    config_dir: Path
    log_dir: Path
    backup_dir: Path
    frontend_dir: Path
    helper_dir: Path
    bind_host: str
    bind_port: int
    hostname: str
    ap_ssid: str
    lan_cidr: str
    guest_cidr: str
    session_ttl_hours: int = 12

    @property
    def schema_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "db" / "schema.sql"

    @property
    def templates_dir(self) -> Path:
        """Directory holding the hostapd/dnsmasq/nftables templates."""
        env = os.environ.get("SAND_TEMPLATES_DIR", "").strip()
        if env:
            return Path(env)
        for candidate in (self.home / "config", _REPO_ROOT / "config"):
            if candidate.exists():
                return candidate
        return _REPO_ROOT / "config"


def load_settings() -> Settings:
    return Settings(
        home=Path(_env("SAND_HOME", "/opt/sandos")),
        db_path=Path(_env("SAND_DB", "/var/lib/sandos/sand.db")),
        config_dir=Path(_env("SAND_CONFIG_DIR", "/etc/sandos")),
        log_dir=Path(_env("SAND_LOG_DIR", "/var/log/sandos")),
        backup_dir=Path(_env("SAND_BACKUP_DIR", "/var/lib/sandos/backups")),
        frontend_dir=Path(_env("SAND_FRONTEND_DIR", str(_REPO_ROOT / "frontend"))),
        helper_dir=Path(_env("SAND_HELPER_DIR", "/usr/local/lib/sandos")),
        bind_host=_env("SAND_BIND_HOST", "127.0.0.1"),
        bind_port=int(_env("SAND_BIND_PORT", "8088")),
        hostname=_env("SAND_HOSTNAME", "Roku-E8C3"),
        ap_ssid=_env("SAND_AP_SSID", "Roku-E8C3"),
        lan_cidr=_env("SAND_LAN_CIDR", "10.0.0.1/24"),
        guest_cidr=_env("SAND_GUEST_CIDR", "10.0.1.1/24"),
    )


settings = load_settings()
