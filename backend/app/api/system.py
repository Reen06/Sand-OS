"""System router — telemetry, service control, reboot/shutdown, settings."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from ..core.privileged import run_helper
from ..core.settings import settings
from ..core.validation import is_valid_ssid, is_valid_hostname
from ..db.repo import Database
from ..services import system as sysinfo
from .deps import get_db, require_auth, require_csrf

router = APIRouter(prefix="/system", tags=["system"])

# Settings safe to expose to the dashboard (secrets excluded).
_PUBLIC_SETTINGS = ("hostname", "ap_ssid", "ap_channel", "guest_ssid",
                    "guest_enabled", "mac_mode_upstream", "killswitch_default",
                    "theme", "setup_complete")


class IdentityBody(BaseModel):
    ap_ssid: Optional[str] = None
    ap_passphrase: Optional[str] = None
    ap_channel: Optional[str] = None

    @field_validator("ap_ssid")
    @classmethod
    def validate_ssid(cls, v):
        if v is not None and not is_valid_ssid(v):
            raise ValueError("SSID must be 1-32 printable ASCII characters")
        return v

    @field_validator("ap_passphrase")
    @classmethod
    def validate_passphrase(cls, v):
        if v is not None and not (8 <= len(v) <= 63):
            raise ValueError("Passphrase must be 8-63 characters")
        return v

    @field_validator("ap_channel")
    @classmethod
    def validate_channel(cls, v):
        valid = {str(c) for c in list(range(1, 15)) + [36, 40, 44, 48]}
        if v is not None and v not in valid:
            raise ValueError("Invalid WiFi channel")
        return v


@router.get("/info")
def info(_=Depends(require_auth)) -> dict:
    return sysinfo.summary()


@router.get("/settings")
def get_settings(db: Database = Depends(get_db), _=Depends(require_auth)) -> dict:
    return {k: db.get_setting(k) for k in _PUBLIC_SETTINGS}


@router.post("/identity")
def save_identity(body: IdentityBody, db: Database = Depends(get_db),
                  _=Depends(require_csrf)) -> dict:
    """Update SSID, passphrase, and/or channel; re-applies AP config immediately."""
    changed = False
    if body.ap_ssid is not None:
        db.set_setting("ap_ssid", body.ap_ssid)
        changed = True
    if body.ap_passphrase is not None:
        db.set_setting("ap_passphrase", body.ap_passphrase)
        changed = True
    if body.ap_channel is not None:
        db.set_setting("ap_channel", body.ap_channel)
        changed = True
    if not changed:
        return {"ok": True, "message": "Nothing to update"}
    res = run_helper("sand-net", "apply", timeout=30)
    if not res.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Settings saved but AP reconfiguration failed: {res.stderr}")
    db.log_event("system", "AP identity updated (SSID/passphrase/channel)")
    return {"ok": True, "message": "AP identity updated and applied"}


@router.get("/services")
def services(_=Depends(require_auth)) -> dict:
    res = run_helper("sand-sys", "service-status")
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
    res = run_helper("sand-sys", "service-restart", name)
    return {"ok": res.ok, "message": res.stdout or res.stderr}


@router.post("/reboot")
def reboot(_=Depends(require_csrf)) -> dict:
    res = run_helper("sand-sys", "reboot")
    return {"ok": res.ok, "message": res.stdout or res.stderr}


@router.post("/shutdown")
def shutdown(_=Depends(require_csrf)) -> dict:
    res = run_helper("sand-sys", "shutdown")
    return {"ok": res.ok, "message": res.stdout or res.stderr}
