"""Read recent logs from systemd-journald.

The ``sand`` service user is added to the ``systemd-journal`` group at install
time, so journalctl is readable without privilege escalation.
"""
from __future__ import annotations

import subprocess

# Friendly log source -> systemd unit. None means the full journal.
UNIT_MAP: dict[str, str | None] = {
    "system": None,
    "dashboard": "sand-dashboard.service",
    "hostapd": "hostapd.service",
    "dnsmasq": "dnsmasq.service",
    "wifi": "NetworkManager.service",
    "firewall": "sand-firewall.service",
    "netapply": "sand-netapply.service",
    "recovery": "sand-recovery.service",
    "watchdog": "sand-watchdog.service",
    "pihole": "pihole-FTL.service",
    "wireguard": "wg-quick@wg0.service",
}


def sources() -> list[str]:
    return list(UNIT_MAP.keys())


def journal(source: str = "system", lines: int = 200) -> dict:
    """Return recent journal lines for a known source."""
    if source not in UNIT_MAP:
        return {"source": source, "available": False, "lines": [],
                "error": "unknown log source"}
    lines = max(1, min(lines, 1000))
    cmd = ["journalctl", "--no-pager", "-n", str(lines), "-o", "short-iso"]
    unit = UNIT_MAP[source]
    if unit:
        cmd += ["-u", unit]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"source": source, "available": False, "lines": [], "error": str(exc)}
    out = [ln for ln in proc.stdout.splitlines() if ln]
    return {
        "source": source,
        "unit": unit,
        "available": proc.returncode == 0 or bool(out),
        "lines": out,
        "error": proc.stderr.strip() if proc.returncode != 0 and not out else "",
    }
