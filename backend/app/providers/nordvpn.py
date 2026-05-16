"""NordVPN provider — placeholder implementing the VPNProvider interface.

Full implementation would use NordVPN's Linux CLI (`nordvpn connect`, etc.)
or generate WireGuard configs via the NordVPN API. For now this returns
meaningful stubs so the UI can surface a "Not configured" state gracefully.
"""
from __future__ import annotations

from typing import Any

from .base import TunnelStatus, VPNProvider


class NordVPNProvider(VPNProvider):
    name = "nordvpn"
    kind = "nordvpn"

    def connect(self, profile: str, **kwargs: Any) -> tuple[bool, str]:
        return False, "NordVPN provider not yet configured"

    def disconnect(self, profile: str) -> tuple[bool, str]:
        return False, "NordVPN provider not yet configured"

    def status(self, profile: str) -> TunnelStatus:
        return TunnelStatus(
            active=False, iface=None, endpoint=None, public_key=None,
            last_handshake=None, rx_bytes=0, tx_bytes=0,
            extra={"note": "NordVPN not configured"},
        )

    def list_profiles(self) -> list[dict]:
        return []
