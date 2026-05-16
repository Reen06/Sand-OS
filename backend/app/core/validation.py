"""Input validators and patterns.

Every value that could reach a system command, config file, or interface name
is validated here against a strict allowlist before use. Combined with the
list-form subprocess calls used throughout the backend, this prevents shell
and config injection.
"""
from __future__ import annotations

import ipaddress
import re

MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
IFACE_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,15}$")
SSID_RE = re.compile(r"^[\x20-\x7e]{1,32}$")          # printable ASCII, 1-32 chars
HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
WG_NAME_RE = re.compile(r"^[a-zA-Z0-9 _-]{1,32}$")
LOG_SOURCE_RE = re.compile(r"^[a-z]{2,16}$")


def normalize_mac(value: str) -> str | None:
    """Normalize and validate a MAC address; return None if invalid."""
    if not value:
        return None
    v = value.strip().lower().replace("-", ":")
    if "." in v and ":" not in v:  # cisco-style aaaa.bbbb.cccc
        hexed = v.replace(".", "")
        if len(hexed) == 12:
            v = ":".join(hexed[i:i + 2] for i in range(0, 12, 2))
    return v if MAC_RE.match(v) else None


def is_valid_iface(value: str) -> bool:
    return bool(value and IFACE_RE.match(value))


def is_valid_ssid(value: str) -> bool:
    return bool(value and SSID_RE.match(value))


def is_valid_hostname(value: str) -> bool:
    return bool(value and len(value) <= 63 and HOSTNAME_RE.match(value))


def is_valid_wg_name(value: str) -> bool:
    return bool(value and WG_NAME_RE.match(value))


def is_valid_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_locally_administered(mac: str) -> bool:
    """True if the MAC has the locally-administered bit set (safe to assign)."""
    norm = normalize_mac(mac)
    if not norm:
        return False
    return bool(int(norm.split(":")[0], 16) & 0b10)


def wifi_psk_error(psk: str, security: str) -> str | None:
    """Validate a WPA pre-shared key; return an error string or None."""
    if security and security.lower() == "open":
        return None
    if not 8 <= len(psk) <= 63:
        return "WiFi password must be 8-63 characters."
    return None
