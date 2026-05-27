"""Pi-hole FTL service integration.

Provides status, query stats, blocking control, query log, and domain list
management. Gracefully handles the case where Pi-hole is not installed or
is temporarily down. DNS failover (flipping dnsmasq from DHCP-only to full
resolver) is triggered here when Pi-hole is unreachable, keeping internet
working for LAN clients.

Pi-hole v6 exposes a local REST API on the configured port (default 8080
after we moved it off 80). Since no password is configured, the API is
accessible without authentication.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from ..core.privileged import run_helper

_INSTALLED_MARKER = "/usr/local/bin/pihole"
_FTL_CONF = "/etc/pihole/pihole-FTL.conf"
_PIHOLE_API = "http://127.0.0.1:8080/api"


def _api(path: str, method: str = "GET",
         body: dict | None = None, timeout: int = 5) -> Any:
    """Call the local Pi-hole v6 API. Returns parsed JSON or raises."""
    url = _PIHOLE_API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _api_safe(path: str, method: str = "GET",
              body: dict | None = None, default: Any = None) -> Any:
    """_api() that swallows errors and returns default."""
    try:
        return _api(path, method=method, body=body)
    except Exception:
        return default


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


def recent_queries(limit: int = 100) -> list[dict]:
    """Return recent DNS queries from Pi-hole v6 API."""
    data = _api_safe(f"/queries?limit={limit}", default={})
    raw = data.get("queries", []) if isinstance(data, dict) else []
    out = []
    for q in raw:
        status_code = q.get("status", 0)
        # Pi-hole v6 status codes: 1=blocked, 2=forwarded, 3=cached, 4=retried, etc.
        status_label = _query_status(status_code)
        out.append({
            "time": q.get("time", 0),
            "domain": q.get("domain", ""),
            "client": q.get("client", {}).get("name") or q.get("client", {}).get("ip", ""),
            "type": q.get("type", "A"),
            "status": status_label,
            "blocked": status_code == 1,
        })
    return out


def top_domains(count: int = 10) -> dict:
    """Return top permitted and top blocked domains."""
    data = _api_safe(f"/stats/top_domains?blocked=false&count={count}", default={})
    top_permitted = [
        {"domain": d.get("domain", ""), "count": d.get("count", 0)}
        for d in (data.get("domains", []) if isinstance(data, dict) else [])
    ]
    data_blocked = _api_safe(f"/stats/top_domains?blocked=true&count={count}", default={})
    top_blocked = [
        {"domain": d.get("domain", ""), "count": d.get("count", 0)}
        for d in (data_blocked.get("domains", []) if isinstance(data_blocked, dict) else [])
    ]
    return {"top_permitted": top_permitted, "top_blocked": top_blocked}


def top_clients(count: int = 10) -> list[dict]:
    """Return top clients by query count."""
    data = _api_safe(f"/stats/top_clients?count={count}", default={})
    return [
        {"client": c.get("name") or c.get("ip", ""),
         "ip": c.get("ip", ""),
         "count": c.get("count", 0)}
        for c in (data.get("clients", []) if isinstance(data, dict) else [])
    ]


def add_to_list(domain: str, list_type: str) -> tuple[bool, str]:
    """Add a domain to the allowlist or denylist.

    list_type: 'allow' | 'deny'
    """
    if list_type not in ("allow", "deny"):
        return False, "list_type must be 'allow' or 'deny'"
    domain = domain.strip().lower()
    if not domain or len(domain) > 253:
        return False, "Invalid domain"
    try:
        _api(f"/domains/{list_type}", method="POST",
             body={"domain": domain, "comment": "Added via SandOS dashboard"})
        return True, f"{domain} added to {list_type}list"
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return False, f"Pi-hole API error {e.code}: {body[:200]}"
    except Exception as exc:
        return False, str(exc)


def remove_from_list(domain: str, list_type: str) -> tuple[bool, str]:
    """Remove a domain from the allowlist or denylist."""
    if list_type not in ("allow", "deny"):
        return False, "list_type must be 'allow' or 'deny'"
    domain = domain.strip().lower()
    try:
        _api(f"/domains/{list_type}/{urllib.request.quote(domain, safe='')}",
             method="DELETE")
        return True, f"{domain} removed from {list_type}list"
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return False, f"Pi-hole API error {e.code}: {body[:200]}"
    except Exception as exc:
        return False, str(exc)


def query_stats_summary() -> dict:
    """Return extended stats from Pi-hole v6 summary API."""
    data = _api_safe("/stats/summary", default={})
    if not isinstance(data, dict):
        return {}
    q = data.get("queries", {})
    return {
        "total": q.get("total", 0),
        "blocked": q.get("blocked", 0),
        "percent_blocked": round(q.get("percent_blocked", 0.0), 1),
        "unique_domains": q.get("unique_domains", 0),
        "forwarded": q.get("forwarded", 0),
        "cached": q.get("cached", 0),
    }


# ------------------------------------------------------------------ internal

def _query_status(code: int) -> str:
    return {
        0: "unknown", 1: "blocked", 2: "forwarded", 3: "cached",
        4: "retried", 5: "retried_dnssec", 6: "in_progress",
        7: "dbbusy", 8: "dbfull", 9: "blocked_spec",
        10: "blocked_gravity", 11: "blocked_regex",
    }.get(code, "forwarded")

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
