"""Overview page — aggregated system and network status.

System metrics and device count are live now. Internet / upstream / VPN /
Pi-hole report ``unknown`` until their respective phases wire them in; the
frontend renders unknown sub-systems gracefully so the dashboard is always
usable, even with nothing else configured.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db.repo import Database
from ..services import network as netsvc
from ..services import pihole as piholesvc
from ..services import system as sysinfo
from ..services import wifi as wifisvc
from .deps import get_db, require_auth

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
def overview(db: Database = Depends(get_db), _=Depends(require_auth)) -> dict:
    upstream = netsvc.upstream_status()
    connected = upstream.get("status") == "connected"
    internet = (wifisvc.captive_portal_check() if connected
                else {"status": "offline", "url": None})
    ph = piholesvc.status()
    return {
        "system": sysinfo.summary(),
        "devices": {"count": db.count_devices()},
        "internet": internet,
        "upstream": {"status": upstream["status"], "ssid": upstream["ssid"]},
        "vpn": {"status": "unknown", "profile": None},
        "pihole": {
            "status": ph["status"],
            "blocking": ph["blocking"],
            "blocked_today": ph["blocked"],
            "queries_today": ph["queries"],
            "block_pct": ph["block_pct"],
            "failover": ph["failover"],
        },
    }
