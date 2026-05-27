"""Read-only networking status.

These functions never mutate the system — they read /sys, /proc, nmcli, iw,
the dnsmasq lease file and `systemctl is-active`. All of that is available to
the unprivileged dashboard user. Networking *changes* go through netapply.py,
which runs as root.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..core.settings import settings

LEASE_FILE = "/var/lib/misc/dnsmasq.leases"
_RESOLVER_CANDIDATES = [
    settings.helper_dir / "sand-resolve-ifaces",
    Path(__file__).resolve().parents[3] / "scripts" / "helpers" / "sand-resolve-ifaces",
]


def _run(cmd: list[str], timeout: int = 8) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout if proc.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return ""


def _is_active(unit: str) -> bool:
    return _run(["systemctl", "is-active", unit]).strip() == "active"


def resolve_interfaces() -> dict:
    """Return {'ap', 'upstream', 'radio_count'} via the resolver helper."""
    out = ""
    for candidate in _RESOLVER_CANDIDATES:
        if candidate.exists():
            out = _run(["bash", str(candidate)])
            if out:
                break
    info = {"ap": "", "upstream": "", "radio_count": 0}
    for line in out.splitlines():
        key, _, val = line.partition("=")
        if key == "AP_IFACE":
            info["ap"] = val.strip()
        elif key == "UPSTREAM_IFACE":
            info["upstream"] = val.strip()
        elif key == "RADIO_COUNT":
            info["radio_count"] = int(val.strip() or 0)
    return info


def _iface_ipv4(iface: str) -> str | None:
    if not iface:
        return None
    out = _run(["ip", "-o", "-4", "addr", "show", "dev", iface])
    for token in out.split():
        if "/" in token and token.count(".") == 3:
            return token.split("/")[0]
    return None


def _station_count(iface: str) -> int:
    if not iface:
        return 0
    out = _run(["iw", "dev", iface, "station", "dump"])
    return out.count("Station ")


def ap_status() -> dict:
    """Access point health — interface, address, services, client count."""
    ifaces = resolve_interfaces()
    ap = ifaces["ap"]
    hostapd_up = _is_active("hostapd")
    dnsmasq_up = _is_active("dnsmasq")
    ip = _iface_ipv4(ap)
    running = bool(ap) and hostapd_up and bool(ip)
    return {
        "interface": ap or None,
        "ip": ip,
        "hostapd": hostapd_up,
        "dnsmasq": dnsmasq_up,
        "clients": _station_count(ap),
        "status": "active" if running else ("down" if ap else "unknown"),
        "radio_count": ifaces["radio_count"],
    }


def upstream_status() -> dict:
    """Upstream WiFi client status (enriched by the WiFi phase)."""
    ifaces = resolve_interfaces()
    up = ifaces["upstream"]
    if not up:
        return {"interface": None, "status": "unknown", "ssid": None, "ip": None}
    state = ""
    for line in _run(["nmcli", "-t", "-f", "DEVICE,STATE", "device"]).splitlines():
        dev, _, st = line.partition(":")
        if dev == up:
            state = st
            break
    ssid = None
    for line in _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi"]).splitlines():
        if line.startswith("yes:"):
            ssid = line.split(":", 1)[1] or None
            break
    connected = state.startswith("connected")
    return {
        "interface": up,
        "status": "connected" if connected else "disconnected",
        "ssid": ssid,
        "ip": _iface_ipv4(up),
    }


def dhcp_leases() -> list[dict]:
    """Parse active DHCP leases from the dnsmasq lease file."""
    leases: list[dict] = []
    try:
        text = Path(LEASE_FILE).read_text()
    except OSError:
        return leases
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            leases.append({
                "expiry": int(parts[0]) if parts[0].isdigit() else 0,
                "mac": parts[1].lower(),
                "ip": parts[2],
                "hostname": parts[3] if parts[3] != "*" else None,
            })
    return leases


def arp_macs(iface: Optional[str] = None) -> set[str]:
    """Return the set of MAC addresses with active ARP entries.

    Reads /proc/net/arp directly — no subprocess needed.  Flags=0x2 means the
    entry is complete (not incomplete/stale).  Optionally filtered to one iface.
    """
    macs: set[str] = set()
    try:
        text = Path("/proc/net/arp").read_text()
    except OSError:
        return macs
    for line in text.splitlines()[1:]:   # skip header
        parts = line.split()
        if len(parts) < 6:
            continue
        _ip, _hwtype, flags, mac, _mask, dev = parts[:6]
        if iface and dev != iface:
            continue
        if flags == "0x2" and mac != "00:00:00:00:00:00":
            macs.add(mac.lower())
    return macs


def _station_macs(iface: str) -> set[str]:
    """Return MAC addresses currently associated with the AP via iw station dump."""
    if not iface:
        return set()
    out = _run(["iw", "dev", iface, "station", "dump"])
    macs: set[str] = set()
    for line in out.splitlines():
        if line.startswith("Station "):
            parts = line.split()
            if len(parts) >= 2:
                macs.add(parts[1].lower())
    return macs


def _arp_ip_by_mac(iface: Optional[str] = None) -> dict[str, str]:
    """Return {mac: ip} from the ARP table (any flag), optionally filtered to one iface."""
    result: dict[str, str] = {}
    try:
        text = Path("/proc/net/arp").read_text()
    except OSError:
        return result
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        ip, _hwtype, _flags, mac, _mask, dev = parts[:6]
        if iface and dev != iface:
            continue
        if mac and mac != "00:00:00:00:00:00":
            result[mac.lower()] = ip
    return result


def connected_devices(ap_iface: Optional[str] = None) -> list[dict]:
    """Return devices currently connected to the AP.

    Primary source: DHCP leases cross-referenced with ARP (for liveness).
    Fallback: iw station dump for devices that are associated but have no
    valid lease — this covers the common case where the dnsmasq lease file
    is stale or the lease has expired while the device stayed connected.
    Expired leases are still used for hostname/IP enrichment of station entries.
    """
    import time
    now = int(time.time())

    # Resolve interface if not provided so callers don't have to.
    if not ap_iface:
        ap_iface = resolve_interfaces().get("ap") or ""

    active_macs = arp_macs(ap_iface)

    # Index ALL leases (including expired) by MAC for hostname/IP enrichment.
    all_leases: dict[str, dict] = {l["mac"]: l for l in dhcp_leases()}

    result: list[dict] = []
    seen_macs: set[str] = set()

    for lease in all_leases.values():
        if lease["expiry"] and lease["expiry"] < now:
            continue
        connected = lease["mac"] in active_macs
        result.append({**lease, "connected": connected})
        seen_macs.add(lease["mac"])

    # Devices associated with the AP but missing a valid DHCP lease.
    # Happens when the lease file is stale (dnsmasq restart, permission error)
    # while clients remain connected. Use expired lease data for hostname/IP.
    if ap_iface:
        arp_ips = _arp_ip_by_mac(ap_iface)
        for mac in _station_macs(ap_iface):
            if mac not in seen_macs:
                stale = all_leases.get(mac, {})
                result.append({
                    "mac": mac,
                    "ip": stale.get("ip") or arp_ips.get(mac),
                    "hostname": stale.get("hostname"),
                    "expiry": 0,
                    "connected": True,
                })

    return result


def internet_check() -> dict:
    """Best-effort reachability probe used by the Overview page."""
    import urllib.request
    try:
        req = urllib.request.Request("http://connectivitycheck.gstatic.com/generate_204",
                                     method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            code = resp.getcode()
        if code == 204:
            return {"status": "online"}
        return {"status": "portal"}        # unexpected body => captive portal
    except Exception:
        return {"status": "offline"}
