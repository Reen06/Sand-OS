"""Pi-hole FTL service integration.

Provides status, query stats, and blocking control. Gracefully handles the
case where Pi-hole is not installed or is temporarily down. DNS failover
(flipping dnsmasq from DHCP-only to full resolver) is triggered here when
Pi-hole is unreachable, keeping internet working for LAN clients.
"""
from __future__ import annotations

import json
from typing import Optional

from ..core.privileged import run_helper

_INSTALLED_MARKER = "/usr/local/bin/pihole"
_FTL_CONF = "/etc/pihole/pihole-FTL.conf"


def installed() -> bool:
    """Return True if the pihole binary is present on this system."""
    import os
    return os.path.isfile(_INSTALLED_MARKER)


def status() -> dict:
    """Return Pi-hole status and aggregated query stats.

    Always returns a dict with these keys:
      installed  bool
      status     "active"|"down"|"not_installed"
      blocking   bool
      queries    int   DNS queries today
      blocked    int   queries blocked today
      block_pct  float percentage blocked
      failover   bool  True when dnsmasq is doing DNS (Pi-hole bypassed)
    """
    if not installed():
        return _not_installed()

    res = run_helper("sand-pihole", "status", timeout=8)
    if not res.ok or not res.stdout:
        return _down(failover=_is_failover())

    raw = res.stdout.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _down(failover=_is_failover())

    ftl_active = data.get("ftl_active", data.get("status") == "active")
    if not ftl_active:
        return _down(failover=_is_failover())

    queries = int(data.get("dns_queries_today", 0))
    blocked = int(data.get("ads_blocked_today", 0))
    block_pct = (blocked / queries * 100.0) if queries > 0 else 0.0
    blocking = data.get("blocking", True)
    if isinstance(blocking, str):
        blocking = blocking.lower() != "disabled"

    return {
        "installed": True,
        "status": "active",
        "blocking": bool(blocking),
        "queries": queries,
        "blocked": blocked,
        "block_pct": round(block_pct, 1),
        "failover": False,
    }


def set_blocking(enabled: bool, duration_mins: Optional[int] = None) -> tuple[bool, str]:
    """Enable or disable Pi-hole ad blocking."""
    if enabled:
        res = run_helper("sand-pihole", "enable", timeout=15)
    elif duration_mins:
        res = run_helper("sand-pihole", "disable-mins", str(duration_mins), timeout=15)
    else:
        res = run_helper("sand-pihole", "disable", timeout=15)
    return res.ok, res.stdout or res.stderr


def restart() -> tuple[bool, str]:
    """Restart the pihole-FTL service."""
    res = run_helper("sand-pihole", "restart", timeout=20)
    return res.ok, res.stdout or res.stderr


def activate_failover() -> tuple[bool, str]:
    """Switch dnsmasq to resolver mode when Pi-hole is down."""
    res = run_helper("sand-pihole", "dns-failover-on", timeout=30)
    return res.ok, res.stdout or res.stderr


def deactivate_failover() -> tuple[bool, str]:
    """Restore dnsmasq to DHCP-only mode once Pi-hole is healthy again."""
    res = run_helper("sand-pihole", "dns-failover-off", timeout=30)
    return res.ok, res.stdout or res.stderr


# ------------------------------------------------------------------ internal

def _is_failover() -> bool:
    """Check DB setting: dns_port != 0 means dnsmasq is acting as resolver."""
    try:
        from ..core.settings import settings
        from ..db.repo import Database
        db = Database(settings.db_path, read_only=True)
        port = db.get_setting("dns_port", "0")
        db.close()
        return port != "0"
    except Exception:
        return False


def _not_installed() -> dict:
    return {
        "installed": False, "status": "not_installed",
        "blocking": False, "queries": 0, "blocked": 0,
        "block_pct": 0.0, "failover": False,
    }


def _down(failover: bool = False) -> dict:
    return {
        "installed": True, "status": "down",
        "blocking": False, "queries": 0, "blocked": 0,
        "block_pct": 0.0, "failover": failover,
    }
