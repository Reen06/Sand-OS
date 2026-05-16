"""Apply the schema and seed install-time defaults.

The schema uses CREATE TABLE IF NOT EXISTS, so init_db is safe to run on
every backend start as well as at install time.
"""
from __future__ import annotations

from pathlib import Path

from ..core.security import new_token
from .repo import Database

_DEFAULTS = {
    "ap_ssid": "Roku-E8C3",
    "hostname": "Roku-E8C3",
    "guest_enabled": "0",
    "guest_ssid": "Roku-E8C3-Guest",
    "mac_mode_upstream": "random",     # random | persistent
    "killswitch_default": "1",
    "theme": "dark",
    "setup_complete": "0",
}


def init_db(db: Database, schema_path: Path) -> None:
    db.executescript(Path(schema_path).read_text())
    _seed_defaults(db)


def _seed_defaults(db: Database) -> None:
    for key, value in _DEFAULTS.items():
        if db.get_setting(key) is None:
            db.set_setting(key, value)
    # Per-install secret used to derive CSRF tokens.
    if db.get_setting("_app_secret") is None:
        db.set_setting("_app_secret", new_token(32))
