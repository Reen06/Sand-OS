"""System router — telemetry, service control, reboot/shutdown, settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.privileged import run_helper
from ..core.settings import settings
from ..db.repo import Database
from ..services import system as sysinfo
from .deps import get_db, require_auth, require_csrf

router = APIRouter(prefix="/system", tags=["system"])

# Settings safe to expose to the dashboard (secrets excluded).
_PUBLIC_SETTINGS = ("hostname", "ap_ssid", "guest_ssid", "guest_enabled",
                    "mac_mode_upstream", "killswitch_default", "theme",
                    "setup_complete")


@router.get("/info")
def info(_=Depends(require_auth)) -> dict:
    return sysinfo.summary()


@router.get("/settings")
def get_settings(db: Database = Depends(get_db), _=Depends(require_auth)) -> dict:
    return {k: db.get_setting(k) for k in _PUBLIC_SETTINGS}


@router.get("/services")
def services(_=Depends(require_auth)) -> dict:
    res = run_helper("roku-sys", "service-status")
    items = []
    for line in res.lines():
        parts = line.split()
        if len(parts) >= 3:
            items.append({"name": parts[0], "active": parts[1],
                          "enabled": parts[2]})
    return {"available": res.ok, "services": items,
            "error": "" if res.ok else res.stderr}


@router.post("/services/{name}/restart")
def restart_service(name: str, _=Depends(require_csrf)) -> dict:
    res = run_helper("roku-sys", "service-restart", name)
    return {"ok": res.ok, "message": res.stdout or res.stderr}


@router.post("/reboot")
def reboot(_=Depends(require_csrf)) -> dict:
    res = run_helper("roku-sys", "reboot")
    return {"ok": res.ok, "message": res.stdout or res.stderr}


@router.post("/shutdown")
def shutdown(_=Depends(require_csrf)) -> dict:
    res = run_helper("roku-sys", "shutdown")
    return {"ok": res.ok, "message": res.stdout or res.stderr}
