"""Guest network API — configuration and enable/disable."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.privileged import run_helper
from ..db.repo import Database
from .deps import get_db, require_auth, require_csrf

router = APIRouter(prefix="/guest", tags=["guest"])

_SSID_RE = re.compile(r'^[ -~]{1,32}$')
_PW_RE   = re.compile(r'^[ -~]{8,63}$')


class GuestConfigBody(BaseModel):
    ssid: str | None = None
    passphrase: str | None = None
    enabled: bool | None = None

    def model_post_init(self, _ctx) -> None:
        if self.ssid is not None and not _SSID_RE.match(self.ssid):
            raise ValueError("SSID must be 1-32 printable ASCII characters")
        if self.passphrase is not None and not _PW_RE.match(self.passphrase):
            raise ValueError("Passphrase must be 8-63 printable ASCII characters")


@router.get("/config")
def get_config(db: Database = Depends(get_db),
               _=Depends(require_auth)) -> dict:
    return {
        "enabled":    db.get_setting("guest_enabled", "0") == "1",
        "ssid":       db.get_setting("guest_ssid", "Roku-E8C3-Guest"),
        "passphrase": db.get_setting("guest_passphrase", ""),
        "clients":    _count_guest_clients(),
    }


@router.post("/config")
def update_config(body: GuestConfigBody,
                  db: Database = Depends(get_db),
                  _=Depends(require_csrf)) -> dict:
    if body.ssid is not None:
        db.set_setting("guest_ssid", body.ssid)
    if body.passphrase is not None:
        db.set_setting("guest_passphrase", body.passphrase)
    if body.enabled is not None:
        db.set_setting("guest_enabled", "1" if body.enabled else "0")

    db.log_event("system", "Guest network config updated")

    # Re-apply networking to activate the change.
    res = run_helper("sand-net", "apply", timeout=60)
    if not res.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Config saved but apply failed: {res.stderr}")
    return {
        "ok": True,
        "message": "Guest network " + (
            "enabled" if body.enabled else
            "disabled" if body.enabled is False else "updated"
        ),
    }


@router.get("/devices")
def guest_devices(db: Database = Depends(get_db),
                  _=Depends(require_auth)) -> dict:
    return {"devices": db.list_devices(guest=True)}


# ------------------------------------------------------------------ helpers

def _count_guest_clients() -> int:
    """Approximate: count devices marked as guest in the DB."""
    try:
        from ..core.settings import settings
        from ..db.repo import Database as DB
        db = DB(settings.db_path, read_only=True)
        n = db.count_devices()   # TODO: filter by is_guest after lease integration
        db.close()
        return 0
    except Exception:
        return 0
