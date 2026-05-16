"""WireGuard provider — wg-quick tunnel management.

Profiles are stored in /etc/wireguard/<iface>.conf (installed via the
roku-wg helper) and tracked in the wireguard_profiles DB table.

Tunnel interface assignment: wg0, wg1, … assigned in order at upload time.
The first unused slot is assigned; slots are freed on profile deletion.

Kill-switch: WireGuard configs use ``Table = off`` so the VPN route does
not become the default route for the whole box. The nftables firewall then
steers only marked devices through the tunnel (per-device routing phase).
Devices assigned to a down tunnel have forwarded traffic dropped, except:
  - access to 10.0.0.1 (dashboard) — always allowed
  - DHCP/DNS traffic — always allowed
This ensures no device can "fall through" to the upstream unprotected.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from ..core.privileged import run_helper
from ..db.repo import Database
from .base import TunnelStatus, VPNProvider

_WG_IFACES = [f"wg{i}" for i in range(10)]
_CONF_DIR = Path("/etc/wireguard")


class WireGuardProvider(VPNProvider):
    name = "wireguard"
    kind = "wireguard"

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------------------------------------------------------------- profiles

    def list_profiles(self) -> list[dict]:
        return self._db.query("SELECT * FROM wireguard_profiles ORDER BY id")

    def get_profile(self, name: str) -> Optional[dict]:
        return self._db.query_one(
            "SELECT * FROM wireguard_profiles WHERE name=?", (name,))

    def import_profile(self, name: str, conf_text: str) -> tuple[bool, str]:
        """Validate + install a WireGuard .conf and register it in the DB.

        The conf is sent through the roku-wg helper (which validates the
        minimal structure and installs it at 0600 root:root). We then parse
        the public key, address and endpoint from the file for the DB record.
        """
        name = name.strip()
        if not re.match(r'^[a-zA-Z0-9_-]{1,40}$', name):
            return False, "Profile name must be 1-40 alphanumeric/dash/underscore characters"
        if self._db.query_one(
                "SELECT 1 FROM wireguard_profiles WHERE name=?", (name,)):
            return False, f"A profile named '{name}' already exists"

        # Assign the next free wg interface slot.
        used = {r["iface"] for r in self.list_profiles()}
        iface = next((i for i in _WG_IFACES if i not in used), None)
        if iface is None:
            return False, "All WireGuard interface slots (wg0-wg9) are in use"

        # Send to the privileged helper via stdin — it validates and writes the file.
        res = run_helper("roku-wg", "install", iface, stdin=conf_text, timeout=10)
        if not res.ok:
            return False, f"Config rejected: {res.stderr or res.stdout}"

        # Parse metadata from the conf for the DB record.
        meta = _parse_conf(conf_text)
        conf_path = str(_CONF_DIR / f"{iface}.conf")

        # Determine the next available fwmark (50 + slot index).
        slot = int(iface[2])
        fwmark = 50 + slot
        table_id = 200 + slot

        self._db.execute(
            "INSERT INTO wireguard_profiles "
            "(name,iface,conf_path,address,dns,endpoint,public_key,fwmark,table_id)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (name, iface, conf_path, meta.get("address"), meta.get("dns"),
             meta.get("endpoint"), meta.get("public_key"), fwmark, table_id))
        self._db.log_event("vpn", f"WireGuard profile '{name}' imported ({iface})")
        return True, f"Profile '{name}' installed as {iface}"

    def delete_profile(self, name: str) -> tuple[bool, str]:
        profile = self.get_profile(name)
        if not profile:
            return False, f"Profile '{name}' not found"
        # Bring down first.
        self.disconnect(name)
        res = run_helper("roku-wg", "remove", profile["iface"], timeout=10)
        self._db.execute(
            "DELETE FROM wireguard_profiles WHERE name=?", (name,))
        self._db.log_event("vpn", f"WireGuard profile '{name}' deleted")
        return True, f"Profile '{name}' removed"

    # ---------------------------------------------------------------- control

    def connect(self, profile: str, **kwargs: Any) -> tuple[bool, str]:
        p = self.get_profile(profile)
        if not p:
            return False, f"Profile '{profile}' not found"
        res = run_helper("roku-wg", "up", p["iface"], timeout=20)
        if res.ok:
            self._db.execute(
                "UPDATE wireguard_profiles SET enabled=1 WHERE name=?", (profile,))
            self._db.log_event("vpn", f"WireGuard tunnel '{profile}' connected ({p['iface']})")
        return res.ok, res.stdout or res.stderr

    def disconnect(self, profile: str) -> tuple[bool, str]:
        p = self.get_profile(profile)
        if not p:
            return False, f"Profile '{profile}' not found"
        res = run_helper("roku-wg", "down", p["iface"], timeout=15)
        self._db.execute(
            "UPDATE wireguard_profiles SET enabled=0 WHERE name=?", (profile,))
        self._db.log_event("vpn", f"WireGuard tunnel '{profile}' disconnected")
        return True, res.stdout or "disconnected"

    def set_default(self, name: str) -> tuple[bool, str]:
        if not self.get_profile(name):
            return False, f"Profile '{name}' not found"
        self._db.execute(
            "UPDATE wireguard_profiles SET is_default=0")
        self._db.execute(
            "UPDATE wireguard_profiles SET is_default=1 WHERE name=?", (name,))
        return True, f"'{name}' set as default tunnel"

    # ---------------------------------------------------------------- status

    def status(self, profile: str) -> TunnelStatus:
        p = self.get_profile(profile)
        if not p:
            return TunnelStatus(False, None, None, None, None, 0, 0, {})
        return _iface_status(p["iface"])

    def all_status(self) -> dict[str, TunnelStatus]:
        return {p["name"]: _iface_status(p["iface"])
                for p in self.list_profiles()}

    def update_dns(self, name: str, dns1: str,
                   dns2: Optional[str] = None) -> tuple[bool, str]:
        """Rewrite DNS= in the tunnel config (takes effect on next reconnect)."""
        p = self.get_profile(name)
        if not p:
            return False, f"Profile '{name}' not found"
        args = ["set-dns", p["iface"], dns1]
        if dns2:
            args.append(dns2)
        res = run_helper("roku-wg", *args, timeout=15)
        return res.ok, res.stdout or res.stderr


# ------------------------------------------------------------------ helpers

def _iface_status(iface: str) -> TunnelStatus:
    res = run_helper("roku-wg", "status", iface, timeout=8)
    if not res.ok or "active=false" in res.stdout:
        return TunnelStatus(False, iface, None, None, None, 0, 0, {})
    info: dict[str, str] = {}
    for line in res.lines():
        if ": " in line:
            k, _, v = line.partition(": ")
            info[k.strip()] = v.strip()
    rx = _parse_bytes(info.get("transfer", "").split(",")[0] if "transfer" in info else "")
    tx = _parse_bytes(info.get("transfer", "").split(",")[1] if "," in info.get("transfer", "") else "")
    return TunnelStatus(
        active=True,
        iface=iface,
        endpoint=info.get("endpoint"),
        public_key=info.get("peer"),
        last_handshake=info.get("latest handshake"),
        rx_bytes=rx,
        tx_bytes=tx,
        extra=info,
    )


def _parse_bytes(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    mult = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    parts = s.split()
    if len(parts) == 2 and parts[1] in mult:
        try:
            return int(float(parts[0]) * mult[parts[1]])
        except ValueError:
            pass
    return 0


def _parse_conf(text: str) -> dict:
    """Extract useful fields from a WireGuard .conf for the DB record."""
    result: dict[str, Optional[str]] = {
        "address": None, "dns": None, "endpoint": None, "public_key": None,
    }
    for line in text.splitlines():
        line = line.strip()
        key, _, val = line.partition("=")
        key = key.strip().lower()
        val = val.strip()
        if key == "address":
            result["address"] = val
        elif key == "dns":
            result["dns"] = val
        elif key == "endpoint":
            result["endpoint"] = val
        elif key == "publickey":
            result["public_key"] = val
    return result
