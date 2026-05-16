"""WiFi API — upstream network scan, connect, disconnect, saved, portal."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from ..services import network as netsvc
from ..services import wifi as wifisvc
from .deps import require_auth, require_csrf

router = APIRouter(prefix="/wifi", tags=["wifi"])

# SSID: 1-32 printable characters (IEEE 802.11 allows any bytes but we
# restrict to printable ASCII to keep shell + DB handling safe).
_SSID_RE = re.compile(r'^[ -~]{1,32}$')
# WPA passphrase: 8-63 printable ASCII characters.
_PW_RE = re.compile(r'^[ -~]{8,63}$')
# MAC: lowercase colon-separated hex.
_MAC_RE = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$')
# UUID.
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class ConnectBody(BaseModel):
    ssid: str
    password: Optional[str] = None

    @field_validator("ssid")
    @classmethod
    def _ssid(cls, v: str) -> str:
        if not _SSID_RE.match(v):
            raise ValueError("SSID must be 1-32 printable ASCII characters")
        return v

    @field_validator("password")
    @classmethod
    def _pw(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _PW_RE.match(v):
            raise ValueError("password must be 8-63 printable ASCII characters")
        return v


class MacBody(BaseModel):
    mac: str

    @field_validator("mac")
    @classmethod
    def _mac(cls, v: str) -> str:
        if not _MAC_RE.match(v.lower()):
            raise ValueError("invalid MAC address")
        return v.lower()


def _upstream_iface() -> str:
    """Return the resolved upstream interface or raise 503."""
    ifaces = netsvc.resolve_interfaces()
    up = ifaces.get("upstream", "")
    if not up:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No upstream WiFi interface detected")
    return up


@router.get("/status")
def wifi_status(_=Depends(require_auth)) -> dict:
    ifaces = netsvc.resolve_interfaces()
    up = ifaces.get("upstream")
    upstream = netsvc.upstream_status()
    portal = wifisvc.captive_portal_check() if upstream.get("status") == "connected" else {
        "status": "offline", "url": None
    }
    mac = wifisvc.get_mac(up) if up else None
    return {
        "interface": up,
        "upstream": upstream,
        "portal": portal,
        "mac": mac,
    }


@router.get("/scan")
def wifi_scan(_=Depends(require_auth)) -> dict:
    iface = _upstream_iface()
    networks = wifisvc.scan_networks(iface)
    saved = {c["name"] for c in wifisvc.saved_connections()}
    for n in networks:
        n["saved"] = n["ssid"] in saved
    return {"networks": networks, "interface": iface}


@router.post("/connect")
def wifi_connect(body: ConnectBody, _=Depends(require_csrf)) -> dict:
    iface = _upstream_iface()
    ok, msg = wifisvc.connect(iface, body.ssid, body.password)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Connection failed: {msg}")
    return {"ok": True, "message": msg}


@router.post("/disconnect")
def wifi_disconnect(_=Depends(require_csrf)) -> dict:
    iface = _upstream_iface()
    ok, msg = wifisvc.disconnect(iface)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Disconnect failed: {msg}")
    return {"ok": True, "message": msg}


@router.get("/saved")
def wifi_saved(_=Depends(require_auth)) -> dict:
    return {"connections": wifisvc.saved_connections()}


@router.delete("/saved/{uuid}")
def wifi_forget(uuid: str, _=Depends(require_csrf)) -> dict:
    if not _UUID_RE.match(uuid):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Invalid connection UUID")
    ok, msg = wifisvc.forget(uuid)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}


@router.get("/portal")
def wifi_portal(_=Depends(require_auth)) -> dict:
    return wifisvc.captive_portal_check()


@router.post("/mac/randomize")
def mac_randomize(_=Depends(require_csrf)) -> dict:
    iface = _upstream_iface()
    ok, result = wifisvc.randomize_mac(iface)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, result)
    return {"ok": True, "mac": result}


@router.post("/mac/set")
def mac_set(body: MacBody, _=Depends(require_csrf)) -> dict:
    iface = _upstream_iface()
    ok, msg = wifisvc.set_mac(iface, body.mac)
    if not ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    return {"ok": True, "message": msg}
