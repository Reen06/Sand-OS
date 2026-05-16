"""VPN provider abstraction.

All providers implement VPNProvider. The dashboard never talks to wg/nmcli
directly — it goes through the provider, which uses the privileged helper.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TunnelStatus:
    active: bool
    iface: Optional[str]
    endpoint: Optional[str]
    public_key: Optional[str]
    last_handshake: Optional[str]
    rx_bytes: int
    tx_bytes: int
    extra: dict[str, Any]


class VPNProvider(ABC):
    name: str
    kind: str

    @abstractmethod
    def connect(self, profile: str, **kwargs: Any) -> tuple[bool, str]:
        """Bring a tunnel up. Returns (ok, message)."""

    @abstractmethod
    def disconnect(self, profile: str) -> tuple[bool, str]:
        """Bring a tunnel down. Returns (ok, message)."""

    @abstractmethod
    def status(self, profile: str) -> TunnelStatus:
        """Current tunnel state for a given profile."""

    @abstractmethod
    def list_profiles(self) -> list[dict]:
        """All configured profiles, including inactive ones."""
