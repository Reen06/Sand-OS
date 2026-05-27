"""Stand-alone display refresh — run by sand-display.service (oneshot).

Usage:
    python -m app.display_update
"""
from __future__ import annotations

import logging
import sys
import traceback

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    try:
        from .services.display import update_display
        update_display()
        log.info("display refreshed")
        return 0
    except ImportError as exc:
        log.error("hardware library missing: %s", exc)
        return 1
    except TimeoutError as exc:
        log.error("e-paper busy timeout: %s", exc)
        return 2
    except Exception as exc:
        log.error("display update failed:\n%s", traceback.format_exc())
        return 3


if __name__ == "__main__":
    sys.exit(main())
