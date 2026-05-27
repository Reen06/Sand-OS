"""Devices API — DHCP lease discovery and per-device metadata."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from ..db.repo import Database
from ..services import firewall as fwsvc
from ..services import network as netsvc
from .deps import get_db, require_auth, require_csrf

router = APIRouter(prefix="/devices", tags=["devices"])

_VALID_BUILTIN_POLICIES = {"direct", "blocked"}


class NicknameBody(BaseModel):
    nickname: str


class PolicyBody(BaseModel):
    policy: str

    @field_validator("policy")
    @classmethod
    def _validate(cls, v: str) -> str:
        if v not in _VALID_BUILTIN_POLICIES and not v.startswith("wg:"):
            raise ValueError("policy must be 'direct', 'blocked', or 'wg:<name>'")
        return v


def _sync_and_list(db: Database) -> list[dict]:
    """Sync live ARP+lease data into DB applying the default policy to new devices."""
    ifaces = netsvc.resolve_interfaces()
    ap_iface = ifaces.get("ap")
    live = netsvc.connected_devices(ap_iface)

    default_policy = db.get_setting("default_device_policy") or "direct"
    firewall_dirty = False

    for d in live:
        is_new = db.get_device(d["mac"]) is None
        if is_new and default_policy != "direct":
            db.upsert_device(d["mac"], ip=d["ip"], hostname=d["hostname"],
                             route_profile=default_policy,
                             blocked=1 if default_policy == "blocked" else 0)
            if default_policy == "blocked":
                firewall_dirty = True
        else:
            db.upsert_device(d["mac"], ip=d["ip"], hostname=d["hostname"])

    if firewall_dirty:
        fwsvc.rebuild_firewall(db)

    connected_macs = {d["mac"] for d in live if d["connected"]}
    rows = db.list_devices()
    result = []
    for row in rows:
        device = dict(row)
        device["connected"] = device["mac"] in connected_macs
        result.append(device)
    result.sort(key=lambda d: (not d["connected"], d.get("last_seen", "") or ""))
    return result


@router.get("")
def list_devices(db: Database = Depends(get_db),
                 _=Depends(require_auth)) -> dict:
    return {"devices": _sync_and_list(db)}


@router.get("/policy")
def get_policy(db: Database = Depends(get_db),
               _=Depends(require_auth)) -> dict:
    return {"policy": db.get_setting("default_device_policy") or "direct"}


@router.patch("/policy")
def set_policy(body: PolicyBody, db: Database = Depends(get_db),
               _=Depends(require_csrf)) -> dict:
    db.set_setting("default_device_policy", body.policy)
    db.log_event("system", f"Default device policy changed to '{body.policy}'")
    return {"ok": True, "policy": body.policy}


@router.patch("/{mac}/nickname")
def set_nickname(mac: str, body: NicknameBody,
                 db: Database = Depends(get_db),
                 _=Depends(require_csrf)) -> dict:
    mac = mac.lower()
    db.upsert_device(mac, nickname=body.nickname.strip())
    return {"ok": True}


@router.delete("/{mac}")
def forget_device(mac: str, db: Database = Depends(get_db),
                  _=Depends(require_csrf)) -> dict:
    if not db.get_device(mac.lower()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    db.delete_device(mac.lower())
    return {"ok": True}
