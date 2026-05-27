"""Pi-hole API — status, blocking toggle, DNS failover control, query log."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from ..services import pihole as piholesvc
from .deps import require_auth, require_csrf

router = APIRouter(prefix="/pihole", tags=["pihole"])

_DOMAIN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)"
    r"+[a-zA-Z]{2,}$|^\*\.(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}$"
)


class BlockingBody(BaseModel):
    enabled: bool
    duration_mins: Optional[int] = None   # only used when enabled=False


class DomainListBody(BaseModel):
    domain: str
    list_type: str  # 'allow' | 'deny'

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v):
        v = v.strip().lower()
        if not _DOMAIN_RE.match(v):
            raise ValueError("Invalid domain name")
        return v

    @field_validator("list_type")
    @classmethod
    def validate_list(cls, v):
        if v not in ("allow", "deny"):
            raise ValueError("list_type must be 'allow' or 'deny'")
        return v


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


@router.get("/queries")
def get_queries(limit: int = Query(default=100, ge=1, le=500),
                _=Depends(require_auth)) -> dict:
    """Recent DNS query log from Pi-hole v6."""
    if not piholesvc.installed():
        return {"queries": [], "installed": False}
    return {"queries": piholesvc.recent_queries(limit), "installed": True}


@router.get("/top")
def get_top(_=Depends(require_auth)) -> dict:
    """Top permitted/blocked domains and top clients."""
    if not piholesvc.installed():
        return {"top_permitted": [], "top_blocked": [], "top_clients": [],
                "installed": False}
    return {**piholesvc.top_domains(), "top_clients": piholesvc.top_clients(),
            "installed": True}


@router.get("/summary")
def get_summary(_=Depends(require_auth)) -> dict:
    """Extended Pi-hole v6 query statistics."""
    if not piholesvc.installed():
        return {"installed": False}
    return {"installed": True, **piholesvc.query_stats_summary()}


@router.post("/list")
def manage_list(body: DomainListBody, _=Depends(require_csrf)) -> dict:
    """Add a domain to the Pi-hole allowlist or denylist."""
    if not piholesvc.installed():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Pi-hole is not installed")
    ok, msg = piholesvc.add_to_list(body.domain, body.list_type)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.delete("/list")
def remove_list(body: DomainListBody, _=Depends(require_csrf)) -> dict:
    """Remove a domain from the Pi-hole allowlist or denylist."""
    if not piholesvc.installed():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Pi-hole is not installed")
    ok, msg = piholesvc.remove_from_list(body.domain, body.list_type)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}
