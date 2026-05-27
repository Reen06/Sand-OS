"""Per-device routing and firewall management.

Builds nftables device-routing rules from the SQLite database and installs
them via the sand-fw helper. The base ruleset (hostapd, NAT, guest isolation)
lives in the nftables template; this module writes only the per-device block.

Routing model:
  Direct   → default table (main), no mark needed, packets routed normally.
  WireGuard → fwmark N, policy routing table 200+slot sends to wg0-wg9.
  Blocked  → fwmark 99, firewall drops forwarded traffic for this mark.

Kill-switch: devices assigned to a WireGuard tunnel that is currently DOWN
have their forwarded traffic dropped (blackhole) by the `fwd` chain, EXCEPT:
  • Access to 10.0.0.1 (the dashboard) — always passes.
  • DHCP (udp 67,68) and DNS (udp/tcp 53) — always passes.
  These exceptions are part of the base template; per-device rules add on top.

Policy routing tables (ip rule + ip route) are set up by sand-apply and
re-applied by sand-firewall.service at boot.
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path
from typing import Optional

from ..core.settings import settings
from ..db.repo import Database

_FWMARK_DIRECT   = 0      # no mark — default routing
_FWMARK_BLOCKED  = 99
_FWMARK_WG_BASE  = 50     # wg0=50, wg1=51, …

# Routing table IDs for WireGuard tunnels.
_TABLE_WG_BASE   = 200    # wg0=200, wg1=201, …
_TABLE_BLACKHOLE = 299

# MAC address regex for validation.
_MAC_RE = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$')


def assign_fwmark(db: Database, mac: str) -> int:
    """Assign a unique fwmark to a device, storing it in the DB.

    Direct devices get fwmark 0 (no mark). WireGuard devices get 50+slot.
    Blocked devices get 99. Marks are stable — once assigned, they stay.
    """
    device = db.get_device(mac)
    if not device:
        return _FWMARK_DIRECT
    existing = device.get("fwmark")
    if existing is not None:
        return int(existing)
    profile = device.get("route_profile", "direct")
    if profile == "blocked":
        mark = _FWMARK_BLOCKED
    elif profile.startswith("wg"):
        slot = _wg_slot(db, profile)
        mark = _FWMARK_WG_BASE + slot if slot is not None else _FWMARK_DIRECT
    else:
        mark = _FWMARK_DIRECT
    if mark != _FWMARK_DIRECT:
        db.execute("UPDATE devices SET fwmark=? WHERE mac=?", (mark, mac))
    return mark


def set_device_route(db: Database, mac: str,
                     profile: str) -> tuple[bool, str]:
    """Update a device's routing profile and rebuild the firewall.

    profile values: 'direct' | 'blocked' | <wireguard profile name>
    """
    if not _MAC_RE.match(mac):
        return False, "Invalid MAC address"
    allowed = {"direct", "blocked"} | {
        r["name"] for r in db.query(
            "SELECT name FROM wireguard_profiles")}
    if profile not in allowed:
        return False, f"Unknown routing profile: {profile!r}"

    device = db.get_device(mac)
    if not device:
        return False, f"Device {mac} not found"

    # Assign new fwmark based on new profile.
    if profile == "blocked":
        mark = _FWMARK_BLOCKED
    elif profile == "direct":
        mark = _FWMARK_DIRECT
    else:
        slot = _wg_slot(db, profile)
        mark = _FWMARK_WG_BASE + slot if slot is not None else _FWMARK_DIRECT

    db.upsert_device(mac, route_profile=profile, fwmark=mark if mark else None)

    # Also update/insert into routing_rules.
    existing_rule = db.query_one(
        "SELECT id FROM routing_rules WHERE device_mac=?", (mac,))
    if existing_rule:
        db.execute(
            "UPDATE routing_rules SET provider=?,profile=?,fwmark=?,updated_at=datetime('now')"
            " WHERE device_mac=?",
            ("direct" if profile == "direct" else
             "blocked" if profile == "blocked" else "wireguard",
             profile if profile not in ("direct", "blocked") else None,
             mark, mac))
    else:
        db.execute(
            "INSERT INTO routing_rules(device_mac,provider,profile,fwmark)"
            " VALUES(?,?,?,?)",
            (mac,
             "direct" if profile == "direct" else
             "blocked" if profile == "blocked" else "wireguard",
             profile if profile not in ("direct", "blocked") else None,
             mark))

    db.log_event("firewall", f"Device {mac} route set to '{profile}' (fwmark={mark})")
    return True, f"Route updated: {mac} → {profile}"


def rebuild_firewall(db: Database) -> tuple[bool, str]:
    """Rebuild the nftables ruleset with current per-device routing rules."""
    from ..core.privileged import run_helper
    res = run_helper("sand-fw", "apply", timeout=30)
    if res.ok:
        db.log_event("firewall", "Firewall ruleset rebuilt")
    else:
        db.log_event("firewall", "Firewall rebuild failed",
                     level="error", detail=res.stderr)
    return res.ok, res.stdout or res.stderr


def device_rules_nft(db: Database) -> tuple[str, str]:
    """Generate per-device nftables rule blocks.

    Returns (mangle_rules, forward_rules):
      mangle_rules   — substituted for # ROKU-MANGLE-RULES (prerouting, priority mangle)
                       Sets the fwmark BEFORE the routing decision so ip rule works.
      forward_rules  — substituted for # ROKU-DEVICE-RULES (forward chain)
                       Kill-switch drops and blocked-device drops.
    """
    ifaces = _resolve_ifaces()
    ap = ifaces.get("ap", "wlan0")
    mangle_rules: list[str] = []
    forward_rules: list[str] = []

    devices = db.query(
        "SELECT mac,ip,fwmark,route_profile FROM devices "
        "WHERE fwmark IS NOT NULL AND fwmark != 0")
    has_blocked = False
    for dev in devices:
        mac = dev["mac"]
        mark = dev["fwmark"]
        if not mac or mark is None:
            continue
        mark = int(mark)
        if mark == _FWMARK_BLOCKED:
            # netdev ingress chain is already bound to the AP interface, so
            # iifname is not needed (and doesn't resolve in this context).
            mangle_rules.append(
                f'        ether saddr {mac} '
                f'meta mark set {_FWMARK_BLOCKED} comment "blocked:{mac}"')
            has_blocked = True
        else:
            mangle_rules.append(
                f'        ether saddr {mac} '
                f'meta mark set {mark} comment "mark:{mac}"')
            # Forward: kill-switch — if mark is set but packet exits on a
            # different interface, the tunnel must be down; drop it.
            slot = mark - _FWMARK_WG_BASE
            wg_iface = f"wg{slot}"
            forward_rules.append(
                f'        meta mark {mark} oifname != "{wg_iface}" '
                f'oifname != "lo" counter drop comment "killswitch:{mac}"')

    if has_blocked:
        forward_rules.insert(0,
            f'        meta mark {_FWMARK_BLOCKED} counter drop comment "blocked"')

    return "\n".join(mangle_rules), "\n".join(forward_rules)


def routing_status(db: Database) -> list[dict]:
    """Return all devices with their routing profile and tunnel status."""
    devices = db.list_devices()
    wg_ifaces = {r["iface"]: r["name"] for r in db.query(
        "SELECT iface, name FROM wireguard_profiles")}
    active_tunnels: set[str] = set()
    for iface in wg_ifaces:
        try:
            out = subprocess.run(
                ["ip", "link", "show", iface],
                capture_output=True, text=True, timeout=3)
            if "UP" in out.stdout:
                active_tunnels.add(iface)
        except Exception:
            pass

    result = []
    for d in devices:
        profile = d.get("route_profile", "direct")
        mark = d.get("fwmark")
        tunnel_active = None
        if profile.startswith("wg"):
            p = db.query_one(
                "SELECT iface FROM wireguard_profiles WHERE name=?", (profile,))
            if p:
                tunnel_active = p["iface"] in active_tunnels
        result.append({
            "mac": d["mac"],
            "ip": d.get("ip"),
            "hostname": d.get("hostname"),
            "nickname": d.get("nickname"),
            "route_profile": profile,
            "fwmark": mark,
            "tunnel_active": tunnel_active,
        })
    return result


# ------------------------------------------------------------------ helpers

def _wg_slot(db: Database, profile_name: str) -> Optional[int]:
    row = db.query_one(
        "SELECT iface FROM wireguard_profiles WHERE name=?", (profile_name,))
    if row and row["iface"].startswith("wg"):
        try:
            return int(row["iface"][2])
        except ValueError:
            pass
    return None


def _resolve_ifaces() -> dict:
    from ..services.network import resolve_interfaces
    return resolve_interfaces()
