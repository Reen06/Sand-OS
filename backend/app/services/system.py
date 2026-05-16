"""System telemetry — CPU, memory, storage, uptime, temperature.

All values are read directly from /proc and /sys; no privileges required.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


def _read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def cpu_temp_c() -> float | None:
    raw = _read("/sys/class/thermal/thermal_zone0/temp")
    return round(int(raw) / 1000, 1) if raw.isdigit() else None


def load_average() -> dict:
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return {"1m": 0.0, "5m": 0.0, "15m": 0.0}
    return {"1m": round(one, 2), "5m": round(five, 2), "15m": round(fifteen, 2)}


def cpu_count() -> int:
    return os.cpu_count() or 1


def memory() -> dict:
    info: dict[str, int] = {}
    for line in _read("/proc/meminfo").splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            info[name.strip()] = int(parts[0])  # kB
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    used = max(total - available, 0)
    return {
        "total_mb": round(total / 1024),
        "used_mb": round(used / 1024),
        "available_mb": round(available / 1024),
        "percent": round(used / total * 100, 1) if total else 0.0,
    }


def storage(path: str = "/") -> dict:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {"total_gb": 0.0, "used_gb": 0.0, "free_gb": 0.0, "percent": 0.0}
    return {
        "total_gb": round(usage.total / 1e9, 1),
        "used_gb": round(usage.used / 1e9, 1),
        "free_gb": round(usage.free / 1e9, 1),
        "percent": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
    }


def uptime_seconds() -> int:
    raw = _read("/proc/uptime").split()
    try:
        return int(float(raw[0])) if raw else 0
    except ValueError:
        return 0


def hostname() -> str:
    return _read("/proc/sys/kernel/hostname") or "roku"


def throttled() -> bool:
    """True if the Pi has reported under-voltage or throttling."""
    raw = _read("/sys/devices/platform/soc/soc:firmware/get_throttled")
    try:
        return int(raw, 0) != 0 if raw else False
    except ValueError:
        return False


def summary() -> dict:
    return {
        "hostname": hostname(),
        "uptime_seconds": uptime_seconds(),
        "cpu_temp_c": cpu_temp_c(),
        "cpu_count": cpu_count(),
        "load": load_average(),
        "memory": memory(),
        "storage": storage(),
        "throttled": throttled(),
        "time": int(time.time()),
    }
