"""VPN API — WireGuard profile management, tunnel control, stats."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..db.repo import Database
from ..providers.wireguard import WireGuardProvider
from .deps import get_db, require_auth, require_csrf

router = APIRouter(prefix="/vpn", tags=["vpn"])

_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]{1,40}$')
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_MAX_CONF_BYTES = 8192


def _wg(db: Database) -> WireGuardProvider:
    return WireGuardProvider(db)


class ProfileActionBody(BaseModel):
    action: str   # connect|disconnect|set-default


@router.get("/profiles")
def list_profiles(db: Database = Depends(get_db),
                  _=Depends(require_auth)) -> dict:
    wg = _wg(db)
    profiles = wg.list_profiles()
    statuses = wg.all_status()
    result = []
    for p in profiles:
        st = statuses.get(p["name"])
        result.append({
            **p,
            "active": st.active if st else False,
            "endpoint": st.endpoint if st else p.get("endpoint"),
            "last_handshake": st.last_handshake if st else None,
            "rx_bytes": st.rx_bytes if st else 0,
            "tx_bytes": st.tx_bytes if st else 0,
        })
    return {"profiles": result}


@router.post("/profiles/upload")
async def upload_profile(
    name: str = Form(...),
    conf: UploadFile = File(...),
    db: Database = Depends(get_db),
    _=Depends(require_csrf),
) -> dict:
    if not _NAME_RE.match(name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Profile name must be 1-40 alphanumeric/dash/underscore characters")
    raw = await conf.read(_MAX_CONF_BYTES + 1)
    if len(raw) > _MAX_CONF_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Config file exceeds 8 KB limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Config file must be UTF-8 text")
    if "[Interface]" not in text or "PrivateKey" not in text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Not a valid WireGuard config (missing [Interface] or PrivateKey)")

    ok, msg = _wg(db).import_profile(name, text)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    return {"ok": True, "message": msg}


@router.post("/profiles/{name}/action")
def profile_action(name: str, body: ProfileActionBody,
                   db: Database = Depends(get_db),
                   _=Depends(require_csrf)) -> dict:
    if not _NAME_RE.match(name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid profile name")
    wg = _wg(db)
    if body.action == "connect":
        ok, msg = wg.connect(name)
    elif body.action == "disconnect":
        ok, msg = wg.disconnect(name)
    elif body.action == "set-default":
        ok, msg = wg.set_default(name)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Unknown action: {body.action!r}")
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.delete("/profiles/{name}")
def delete_profile(name: str,
                   db: Database = Depends(get_db),
                   _=Depends(require_csrf)) -> dict:
    if not _NAME_RE.match(name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid profile name")
    ok, msg = _wg(db).delete_profile(name)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    return {"ok": True, "message": msg}


@router.get("/profiles/{name}/status")
def profile_status(name: str,
                   db: Database = Depends(get_db),
                   _=Depends(require_auth)) -> dict:
    if not _NAME_RE.match(name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid profile name")
    wg = _wg(db)
    p = wg.get_profile(name)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Profile '{name}' not found")
    st = wg.status(name)
    return {
        "name": name,
        "iface": p["iface"],
        "active": st.active,
        "endpoint": st.endpoint or p.get("endpoint"),
        "last_handshake": st.last_handshake,
        "rx_bytes": st.rx_bytes,
        "tx_bytes": st.tx_bytes,
        "killswitch": bool(p.get("killswitch", True)),
        "is_default": bool(p.get("is_default", False)),
    }
