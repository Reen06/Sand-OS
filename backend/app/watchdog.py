"""Roku-E8C3 health watchdog.

Runs as root every 2 minutes via sand-watchdog.timer. Checks:
  1. Access point (hostapd + dnsmasq) — restart if down.
  2. Dashboard (sand-dashboard) — restart if down.
  3. Pi-hole FTL — if down for N consecutive ticks, activate DNS failover.
  4. USB adapter plug/unplug — re-apply networking if radio count changed.

Progress goes to stdout (journald). All decisions are logged to the DB for
the Logs page.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .core.settings import settings
from .db.repo import Database
from .services import network as netsvc
from .services import pihole as piholesvc

PIHOLE_FAIL_THRESHOLD = 3   # consecutive ticks before DNS failover activates
_TICK_KEY = "_watchdog_pihole_fails"
_RADIO_KEY = "_watchdog_last_radio_count"


def log(msg: str) -> None:
    print(f"[watchdog] {msg}", flush=True)


def _is_active(unit: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", unit],
                           capture_output=True, text=True, timeout=6)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def _restart(unit: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "restart", unit],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def check_ap(db: Database) -> None:
    ap = netsvc.ap_status()
    if ap["status"] == "active":
        log(f"AP OK ({ap['interface']} {ap['ip']}, {ap['clients']} clients)")
        return
    log(f"AP not active ({ap['status']}) — re-applying networking")
    from . import netapply
    netapply.apply_networking(db)
    db.log_event("system", "Watchdog: re-applied networking (AP was down)",
                 level="warn")


def check_dashboard(db: Database) -> None:
    if _is_active("sand-dashboard"):
        return
    log("Dashboard not active — restarting")
    ok = _restart("sand-dashboard")
    db.log_event("system",
                 "Watchdog: dashboard restarted" if ok
                 else "Watchdog: dashboard restart failed",
                 level="warn" if ok else "error")


def check_pihole(db: Database) -> None:
    if not piholesvc.installed():
        return
    ph = piholesvc.status()
    if ph["status"] == "active":
        # If failover was active, deactivate it now that Pi-hole is healthy.
        if ph.get("failover"):
            log("Pi-hole recovered — restoring normal DNS")
            piholesvc.deactivate_failover()
            db.log_event("system", "Watchdog: Pi-hole recovered, DNS failover cleared")
        # Reset failure counter.
        db.set_setting(_TICK_KEY, "0")
        return

    fails = int(db.get_setting(_TICK_KEY, "0") or 0) + 1
    db.set_setting(_TICK_KEY, str(fails))
    log(f"Pi-hole FTL down (consecutive ticks: {fails})")

    if fails == 1:
        # First failure — try to restart.
        log("Attempting pihole-FTL restart")
        ok = _restart("pihole-FTL")
        db.log_event("system",
                     "Watchdog: pihole-FTL restarted" if ok
                     else "Watchdog: pihole-FTL restart failed",
                     level="warn" if ok else "error")
    elif fails >= PIHOLE_FAIL_THRESHOLD and not ph.get("failover"):
        log(f"Pi-hole down for {fails} ticks — activating DNS failover")
        piholesvc.activate_failover()
        db.log_event("system",
                     f"Watchdog: DNS failover activated after {fails} failed checks",
                     level="warn")


def check_usb_adapter(db: Database) -> None:
    """Detect USB WiFi adapter plug/unplug and re-apply networking if needed."""
    ifaces = netsvc.resolve_interfaces()
    current_radios = ifaces.get("radio_count", 0)
    last_radios = int(db.get_setting(_RADIO_KEY, str(current_radios)) or current_radios)
    if current_radios == last_radios:
        return
    log(f"Radio count changed {last_radios} → {current_radios} — re-applying networking")
    db.set_setting(_RADIO_KEY, str(current_radios))
    from . import netapply
    netapply.apply_networking(db)
    db.log_event("system",
                 f"Watchdog: USB adapter change detected ({last_radios}→{current_radios}), networking re-applied",
                 level="warn")


def main() -> int:
    if os.geteuid() != 0:
        log("must run as root")
        return 1

    db = Database(settings.db_path)
    try:
        check_ap(db)
        check_dashboard(db)
        check_pihole(db)
        check_usb_adapter(db)
        log("watchdog tick complete")
        return 0
    except Exception as exc:
        log(f"watchdog error: {exc}")
        try:
            db.log_event("system", f"Watchdog error: {exc}", level="error")
        except Exception:
            pass
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
