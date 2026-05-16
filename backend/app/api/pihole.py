"""Pi-hole API — status, blocking toggle, DNS failover control."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services import pihole as piholesvc
from .deps import require_auth, require_csrf

router = APIRouter(prefix="/pihole", tags=["pihole"])


class BlockingBody(BaseModel):
    enabled: bool
    duration_mins: Optional[int] = None   # only used when enabled=False


@router.get("/status")
def pihole_status(_=Depends(require_auth)) -> dict:
    return piholesvc.status()


@router.post("/blocking")
def set_blocking(body: BlockingBody, _=Depends(require_csrf)) -> dict:
    if not piholesvc.installed():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Pi-hole is not installed")
    ok, msg = piholesvc.set_blocking(body.enabled, body.duration_mins)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.post("/restart")
def restart_pihole(_=Depends(require_csrf)) -> dict:
    if not piholesvc.installed():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Pi-hole is not installed")
    ok, msg = piholesvc.restart()
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.post("/failover/on")
def failover_on(_=Depends(require_csrf)) -> dict:
    """Force DNS failover: dnsmasq acts as resolver while Pi-hole is down."""
    ok, msg = piholesvc.activate_failover()
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.post("/failover/off")
def failover_off(_=Depends(require_csrf)) -> dict:
    """Restore normal DNS: Pi-hole handles queries, dnsmasq is DHCP-only."""
    ok, msg = piholesvc.deactivate_failover()
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}
