"""Watchdog entry point. Run as: python -m watchdog

Loops forever, every SCAN_INTERVAL_SECONDS:
  1. requeue stalled 'processing' tasks
  2. cleanup orphan chromium processes (from stalled generate_pdf tasks)
Designed to run as its own systemd service, independent of the FastAPI app.
"""
import logging
import os
import random
import signal
import time

import psycopg2

from watchdog.config import SCAN_INTERVAL_SECONDS
from watchdog.scanner import requeue_stalled, cleanup_orphan_chromium

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watchdog] %(levelname)s %(message)s",
)
logger = logging.getLogger("HHB_B2B")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")

_running = True


def _handle_signal(signum, frame):
    global _running
    logger.info(f"[watchdog] received signal {signum}, stopping after current scan.")
    _running = False


def _connect():
    return psycopg2.connect(DATABASE_URL)


def compute_backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter, capped at attempt 6.

    Returns seconds to wait before a failed task becomes claimable again.
    Base = 2^attempt, jitter multiplies by (1 + random()) in [1, 2).
    Cap at attempt 6 so we never compute 2^20 seconds.
    """
    capped = min(attempt, 6)
    base = 2 ** capped
    return base * (1 + random.random())


def run_once() -> None:
    """One scan iteration."""
    conn = _connect()
    conn.autocommit = True
    try:
        requeued = requeue_stalled(conn)
        cleanup_orphan_chromium(older_than_sec=600)
        if requeued:
            logger.info(f"[watchdog] scan complete: {requeued} task(s) requeued.")
        else:
            logger.info("[watchdog] scan complete: no stalled tasks.")
    finally:
        conn.close()


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    # Mask the password in logs.
    safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    logger.info(f"[watchdog] starting. Scan every {SCAN_INTERVAL_SECONDS}s. DB={safe_url}")
    while _running:
        try:
            run_once()
        except Exception as e:
            logger.error(f"[watchdog] scan error: {e}", exc_info=True)
        # Sleep in small increments so signals are picked up promptly.
        for _ in range(SCAN_INTERVAL_SECONDS):
            if not _running:
                break
            time.sleep(1)
    logger.info("[watchdog] stopped.")


if __name__ == "__main__":
    main()
