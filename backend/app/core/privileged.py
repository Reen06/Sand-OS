"""Run whitelisted privileged helper scripts via sudo.

The dashboard service runs as the unprivileged ``roku`` user. Every action
needing root goes through a fixed helper script in ROKU_HELPER_DIR, invoked
via ``sudo -n`` under a NOPASSWD rule scoped to exactly those scripts.
Arguments are always passed as a list (never a shell string) and the helper
name is checked against an allowlist, so untrusted input cannot reach a shell.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .settings import settings

# Helper scripts installed to ROKU_HELPER_DIR. Each performs strict argument
# validation of its own; this set is the outer allowlist.
HELPERS = {"roku-sys", "roku-net", "roku-fw", "roku-wifi", "roku-wg", "roku-pihole"}


@dataclass
class HelperResult:
    ok: bool
    code: int
    stdout: str
    stderr: str

    def lines(self) -> list[str]:
        return [ln for ln in self.stdout.splitlines() if ln]


def run_helper(name: str, *args: str, timeout: int = 30,
               stdin: str | None = None) -> HelperResult:
    """Invoke a privileged helper. Raises ValueError for an unknown helper."""
    if name not in HELPERS:
        raise ValueError(f"unknown helper: {name!r}")
    for a in args:
        if not isinstance(a, str):
            raise TypeError("helper arguments must be strings")
        if "\x00" in a:
            raise ValueError("null byte in helper argument")
    cmd = ["sudo", "-n", str(settings.helper_dir / name), *args]
    try:
        proc = subprocess.run(cmd, input=stdin, capture_output=True,
                              text=True, timeout=timeout)
        return HelperResult(proc.returncode == 0, proc.returncode,
                            proc.stdout.strip(), proc.stderr.strip())
    except subprocess.TimeoutExpired:
        return HelperResult(False, -1, "", f"helper {name} timed out")
    except FileNotFoundError:
        return HelperResult(False, -1, "", f"helper {name} not installed")
    except PermissionError:
        return HelperResult(False, -1, "", f"helper {name} not permitted")
