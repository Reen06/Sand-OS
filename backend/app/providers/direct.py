"""Direct provider — no VPN tunnel, traffic goes straight to upstream."""
from __future__ import annotations

from typing import Any

from .base import TunnelStatus, VPNProvider


class DirectProvider(VPNProvider):
    name = "direct"
    kind = "direct"

    def connect(self, profile: str = "direct", **kwargs: Any) -> tuple[bool, str]:
        return True, "Direct routing active (no tunnel)"

    def disconnect(self, profile: str = "direct") -> tuple[bool, str]:
        return True, "Direct routing has no tunnel to disconnect"

    def status(self, profile: str = "direct") -> TunnelStatus:
        return TunnelStatus(
            active=True, iface=None, endpoint=None, public_key=None,
            last_handshake=None, rx_bytes=0, tx_bytes=0,
            extra={"note": "no tunnel — traffic goes directly to upstream"},
        )

    def list_profiles(self) -> list[dict]:
        return [{"name": "direct", "kind": "direct", "enabled": True}]
