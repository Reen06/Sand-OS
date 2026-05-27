"""Upstream WiFi service — nmcli wrappers and captive portal detection.

Read-only queries (scan list, saved connections) run via the sand-wifi sudo
helper to ensure the rescan forces fresh data. All state-changing calls
(connect, disconnect, forget) also go through the helper.

Captive portal detection probes a known URL; if the response is not HTTP 204
the upstream is behind a portal and we return the redirect URL so the frontend
can surface an "Open portal" link.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.error
from typing import Optional

from ..core.privileged import run_helper

# Standard connectivity check endpoint — returns 204 when internet is clear.
_PROBE_URL = "http://connectivitycheck.gstatic.com/generate_204"
_PROBE_TIMEOUT = 5
# Fallback URL for DNS-hijack portals: a plain HTTP page that never uses HTTPS,
# specifically designed to be intercepted and redirected by captive portals.
_PORTAL_TRIGGER_URL = "http://neverssl.com"

# BSSID escaping in nmcli terse mode: colons in values are preceded by a
# backslash.  We split on unescaped colons then strip the escapes.
_COLON_SPLIT = re.compile(r"(?<!\\):")


def _terse_split(line: str) -> list[str]:
    """Split a nmcli terse line on unescaped colons, unescape values."""
    parts = _COLON_SPLIT.split(line)
    return [p.replace("\\:", ":") for p in parts]


def scan_networks(iface: Optional[str] = None) -> list[dict]:
    """Return available WiFi networks visible from `iface` (or all radios)."""
    args = ["scan"]
    if iface:
        args.append(iface)
    res = run_helper("sand-wifi", *args, timeout=20)
    networks: list[dict] = []
    seen: set[str] = set()
    for line in res.lines():
        parts = _terse_split(line)
        if len(parts) < 6:
            continue
        ssid, bssid, signal, security, chan, freq = (parts + [""] * 6)[:6]
        ssid = ssid.strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        try:
            sig = int(signal)
        except ValueError:
            sig = 0
        networks.append({
            "ssid": ssid,
            "bssid": bssid.strip(),
            "signal": sig,
            "bars": _bars(sig),
            "security": _security_label(security.strip()),
            "open": not security.strip() or security.strip().upper() == "--",
            "channel": chan.strip(),
            "freq": freq.strip(),
        })
    networks.sort(key=lambda n: n["signal"], reverse=True)
    return networks


def saved_connections() -> list[dict]:
    """Return saved WiFi connections from NetworkManager."""
    res = run_helper("sand-wifi", "saved", timeout=10)
    conns: list[dict] = []
    for line in res.lines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            uuid, name = parts
            conns.append({"uuid": uuid.strip(), "name": name.strip()})
    return conns


def connect(iface: str, ssid: str, password: Optional[str]) -> tuple[bool, str]:
    """Connect the upstream interface to a WiFi network."""
    if password:
        res = run_helper("sand-wifi", "connect", iface, ssid, password, timeout=40)
    else:
        res = run_helper("sand-wifi", "connect-open", iface, ssid, timeout=40)
    msg = res.stdout or res.stderr or ("connected" if res.ok else "connection failed")
    return res.ok, msg


def disconnect(iface: str) -> tuple[bool, str]:
    """Disconnect the upstream interface."""
    res = run_helper("sand-wifi", "disconnect", iface, timeout=15)
    msg = res.stdout or res.stderr or ("disconnected" if res.ok else "disconnect failed")
    return res.ok, msg


def forget(uuid: str) -> tuple[bool, str]:
    """Delete a saved connection by UUID."""
    res = run_helper("sand-wifi", "forget", uuid, timeout=10)
    msg = res.stdout or res.stderr or ("forgotten" if res.ok else "delete failed")
    return res.ok, msg


def get_mac(iface: str) -> Optional[str]:
    """Return the current hardware/effective MAC of an interface."""
    res = run_helper("sand-wifi", "mac-get", iface, timeout=5)
    return res.stdout.strip() if res.ok else None


def set_mac(iface: str, mac: str) -> tuple[bool, str]:
    """Set a specific MAC address on the interface."""
    res = run_helper("sand-wifi", "mac-set", iface, mac, timeout=10)
    return res.ok, res.stdout or res.stderr


def randomize_mac(iface: str) -> tuple[bool, str]:
    """Assign a random locally-administered MAC to the interface."""
    res = run_helper("sand-wifi", "mac-random", iface, timeout=10)
    return res.ok, res.stdout.strip() if res.ok else res.stderr


def portal_touch(url: str) -> dict:
    """Fetch a captive portal URL from the Pi's upstream interface.

    Most free-WiFi portals (hotel, café, airport) authenticate by IP or MAC on
    first HTTP contact.  Because SandOS NATs all client traffic, the portal sees
    only the Pi's upstream (wlan1) IP.  Fetching the portal URL here — from the
    Pi itself — is therefore enough to authenticate every device on the LAN.

    We bind the request to the upstream interface's IP so that on networks that
    share the AP subnet (e.g. both on 10.0.0.0/24) the request doesn't go out
    the wrong interface.

    Returns {"online": True} when post-touch connectivity check passes, or
    {"online": False, "url": <final-url>} so the frontend can show the user a
    direct link to a credential form if auto-auth wasn't sufficient.
    """
    from ..services.network import upstream_status as _up_status

    # Determine the upstream source address to bind to.
    source_addr: tuple[str, int] | None = None
    try:
        up = _up_status()
        if up.get("ip"):
            source_addr = (up["ip"], 0)
    except Exception:
        pass

    final_url = url
    try:
        # Use a custom opener that binds to the upstream IP so the OS routes
        # the connection out wlan1 even when the portal IP is on the same
        # subnet as the AP.
        import http.client
        import socket

        class _BoundHTTPHandler(urllib.request.HTTPHandler):
            def http_open(self, req):
                def _make_conn(host, **kw):
                    conn = http.client.HTTPConnection(host, **kw)
                    if source_addr:
                        conn.source_address = source_addr
                    return conn
                return self.do_open(_make_conn, req)

        opener = urllib.request.build_opener(_BoundHTTPHandler)
        req = urllib.request.Request(
            url,
            headers={"User-Agent":
                     "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                     "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                     "Mobile/15E148 Safari/604.1"},
        )
        with opener.open(req, timeout=10) as resp:
            final_url = resp.geturl() or url
            resp.read(16384)
    except urllib.error.HTTPError as exc:
        loc = exc.headers.get("Location")
        final_url = loc if loc else url
    except Exception:
        pass

    check = captive_portal_check()
    if check["status"] == "online":
        return {"online": True}
    return {"online": False, "url": final_url}


def captive_portal_check() -> dict:
    """Probe for a captive portal on the current upstream connection.

    Returns {"status": "online"|"portal"|"offline", "url": str|None}.
    url is the portal login page when status is "portal".

    Two interception patterns handled:
    - HTTP redirect: portal returns 302 → urllib follows → final URL differs from probe
    - DNS hijack: portal serves content at the probe URL → final URL == probe URL;
      we return _PORTAL_TRIGGER_URL so the browser triggers the redirect itself.
    """
    try:
        req = urllib.request.Request(_PROBE_URL, method="GET")
        with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
            if resp.getcode() == 204:
                return {"status": "online", "url": None}
            # Non-204: portal is serving content.
            final_url = resp.geturl() or ""
            # DNS-hijack portals serve at the probe URL with no redirect.
            if not final_url or final_url == _PROBE_URL:
                return {"status": "portal", "url": _PORTAL_TRIGGER_URL}
            return {"status": "portal", "url": final_url}
    except urllib.error.HTTPError as exc:
        loc = exc.headers.get("Location")
        if loc:
            return {"status": "portal", "url": loc}
        return {"status": "offline", "url": None}
    except urllib.error.URLError as exc:
        # SSL error on portal redirect → portal is present but over HTTPS
        cause = str(getattr(exc, "reason", exc))
        if "SSL" in cause or "CERTIFICATE" in cause.upper():
            return {"status": "portal", "url": _PORTAL_TRIGGER_URL}
        return {"status": "offline", "url": None}
    except Exception:
        return {"status": "offline", "url": None}


# ------------------------------------------------------------------ internal

def _bars(signal: int) -> int:
    """Convert nmcli signal (0-100) to a 0-4 bar rating."""
    if signal >= 80:
        return 4
    if signal >= 60:
        return 3
    if signal >= 40:
        return 2
    if signal >= 20:
        return 1
    return 0


def _security_label(raw: str) -> str:
    if not raw or raw in ("--", ""):
        return "Open"
    if "WPA3" in raw:
        return "WPA3"
    if "WPA2" in raw:
        return "WPA2"
    if "WPA" in raw:
        return "WPA"
    if "WEP" in raw:
        return "WEP"
    return raw
