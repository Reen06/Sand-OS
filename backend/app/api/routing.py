"""Per-device routing API — assign routing profiles, rebuild firewall."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..db.repo import Database
from ..services import firewall as fwsvc
from .deps import get_db, require_auth, require_csrf

router = APIRouter(prefix="/routing", tags=["routing"])

_MAC_RE = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$')


class RouteBody(BaseModel):
    mac: str
    profile: str      # "direct" | "blocked" | <wireguard profile name>


@router.get("/rules")
def list_rules(db: Database = Depends(get_db),
               _=Depends(require_auth)) -> dict:
    return {"devices": fwsvc.routing_status(db)}


@router.post("/rules")
def set_rule(body: RouteBody,
             db: Database = Depends(get_db),
             _=Depends(require_csrf)) -> dict:
    mac = body.mac.lower().strip()
    if not _MAC_RE.match(mac):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Invalid MAC address")
    ok, msg = fwsvc.set_device_route(db, mac, body.profile)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    # Rebuild firewall to apply the new rule.
    fwsvc.rebuild_firewall(db)
    return {"ok": True, "message": msg}


@router.post("/rebuild")
def rebuild(db: Database = Depends(get_db),
            _=Depends(require_csrf)) -> dict:
    """Force a full nftables rebuild from the current DB state."""
    ok, msg = fwsvc.rebuild_firewall(db)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.get("/profiles")
def list_profiles(db: Database = Depends(get_db),
                  _=Depends(require_auth)) -> dict:
    """Available routing profiles: direct, blocked, plus WireGuard tunnels."""
    wg = db.query("SELECT name, iface, enabled FROM wireguard_profiles")
    profiles = [
        {"name": "direct",  "label": "Direct (no VPN)", "kind": "direct"},
        {"name": "blocked", "label": "Blocked",         "kind": "blocked"},
    ] + [
        {"name": r["name"],
         "label": r["name"],
         "kind": "wireguard",
         "iface": r["iface"],
         "active": bool(r["enabled"])}
        for r in wg
    ]
    return {"profiles": profiles}
