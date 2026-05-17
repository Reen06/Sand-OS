"""Boot-time recovery check.

Runs as root after the dashboard starts (sand-recovery.service). It guarantees
the device is always reachable:

  * If the recovery flag file is present (a user can `touch` it from another
    machine by editing the SD card), it forces a clean, safe access point and
    ignores any saved upstream/VPN state.
  * Otherwise it verifies the access point and dashboard are running and
    repairs them if not.

Progress is written to stdout (captured by the journal).

    python -m app.recovery
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import netapply
from .core.settings import settings
from .db.repo import Database
from .services import network

RECOVERY_FLAG = "/boot/firmware/sand-recovery"


def log(msg: str) -> None:
    print(f"[recovery] {msg}", flush=True)


def _active(unit: str) -> bool:
    try:
        out = subprocess.run(["systemctl", "is-active", unit],
                             capture_output=True, text=True, timeout=8)
        return out.stdout.strip() == "active"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main() -> int:
    if os.geteuid() != 0:
        log("must run as root")
        return 1

    db = Database(settings.db_path, read_only=True)
    try:
        flag = Path(RECOVERY_FLAG)

        if flag.exists():
            log("recovery flag present — forcing safe access-point mode")
            netapply.apply_networking(db)
            try:
                flag.unlink()
            except OSError:
                pass
            log("safe access-point mode applied; recovery flag cleared")
            return 0

        ap = network.ap_status()
        if ap["status"] != "active":
            log(f"access point not active ({ap['status']}) — re-applying networking")
            netapply.apply_networking(db)
        else:
            log(f"access point healthy on {ap['interface']} ({ap['ip']})")

        if not _active("sand-dashboard"):
            log("dashboard service not active — restarting")
            subprocess.run(["systemctl", "restart", "sand-dashboard"], timeout=20)

        log("recovery check complete")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
