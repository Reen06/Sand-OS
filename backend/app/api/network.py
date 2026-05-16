"""Networking router — access point / upstream status and cutover controls."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ..core.privileged import run_helper
from ..services import network
from .deps import require_auth, require_csrf

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/status")
def network_status(_=Depends(require_auth)) -> dict:
    return {
        "interfaces": network.resolve_interfaces(),
        "ap": network.ap_status(),
        "upstream": network.upstream_status(),
        "cutover_pending": Path("/run/roku-cutover-pending").exists(),
    }


@router.post("/apply")
def network_apply(_=Depends(require_csrf)) -> dict:
    """Re-apply the access point, DHCP and firewall from current settings."""
    res = run_helper("roku-net", "apply", timeout=120)
    return {"ok": res.ok, "output": res.stdout or res.stderr}


@router.post("/cutover/confirm")
def cutover_confirm(_=Depends(require_csrf)) -> dict:
    """Confirm a pending cutover, cancelling the timed auto-rollback."""
    res = run_helper("roku-sys", "cutover-confirm")
    return {"ok": res.ok, "message": res.stdout or res.stderr}
