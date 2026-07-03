"""Watchdog DB operations. No loop, no process management — just the SQL.

Each function takes a *raw sync psycopg2 connection* (autocommit=True) and
returns a count of affected rows. Keeps the loop logic in __main__ testable.
"""
import logging

from watchdog.config import TASK_TIMEOUTS, DEFAULT_STALL_TIMEOUT

logger = logging.getLogger("HHB_B2B")


def requeue_stalled(conn) -> int:
    """Return stalled 'processing' tasks to 'pending'.

    A task is stalled if it has been in 'processing' longer than the stall
    timeout for its task_type. We run one UPDATE per task_type because the
    timeout differs; this also keeps the query plan simple.

    Returns the total number of requeued rows.
    """
    total = 0
    cur = conn.cursor()
    try:
        for task_type, timeout in TASK_TIMEOUTS.items():
            cur.execute(
                """
                UPDATE job_queue
                   SET status = 'pending',
                       claimed_at = NULL,
                       updated_at = now(),
                       error_message = COALESCE(error_message, '')
                            || E'\n[watchdog] requeued after stall (' || %s || E' s)'
                 WHERE status = 'processing'
                   AND task_type = %s
                   AND claimed_at < now() - (%s || ' seconds')::interval
                """,
                (str(timeout), task_type, str(timeout)),
            )
            total += cur.rowcount
    finally:
        cur.close()

    # Default-timeout sweep for task types not in TASK_TIMEOUTS.
    excluded = tuple(TASK_TIMEOUTS.keys())
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE job_queue
               SET status = 'pending',
                   claimed_at = NULL,
                   updated_at = now(),
                   error_message = COALESCE(error_message, '')
                        || E'\n[watchdog] requeued after stall (default)'
             WHERE status = 'processing'
               AND claimed_at < now() - (%s || ' seconds')::interval
               AND (task_type NOT IN %s)
            """,
            (str(DEFAULT_STALL_TIMEOUT), excluded),
        )
        total += cur.rowcount
    finally:
        cur.close()

    if total:
        logger.info(f"[watchdog] requeued {total} stalled task(s).")
    return total


# ----------------------------------------------------------------------
# Orphan Chromium cleanup (for stalled generate_pdf tasks)
# ----------------------------------------------------------------------
import os
import time
from typing import Callable, List, Tuple


def _list_chromium_procs(older_than_sec: int = 300) -> List[Tuple[int, str, int]]:
    """Return [(pid, name, age_seconds)] for chromium-like processes.

    Uses psutil if available; returns [] on any failure (best-effort —
    cleanup must never crash the watchdog).
    """
    try:
        import psutil
    except ImportError:
        logger.warning("[watchdog] psutil not installed — Chromium cleanup disabled.")
        return []

    out = []
    now = time.time()
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            name = (proc.info["name"] or "").lower()
            if not any(token in name for token in ("chromium", "chrome", "headless")):
                continue
            age = int(now - proc.info["create_time"])
            out.append((proc.info["pid"], name, age))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def cleanup_orphan_chromium(
    older_than_sec: int = 300,
    killer: Callable[[int], None] = None,
) -> int:
    """Kill chromium-like processes older than `older_than_sec`.

    `killer` is injectable for testing; defaults to os.kill on POSIX or
    taskkill on Windows. Returns the number of killed processes.
    """
    if killer is None:
        killer = _default_killer

    killed = 0
    for pid, _name, age in _list_chromium_procs(older_than_sec):
        if age >= older_than_sec:
            try:
                killer(pid)
                killed += 1
                logger.info(f"[watchdog] killed orphan chromium pid={pid} age={age}s")
            except Exception as e:
                logger.warning(f"[watchdog] failed to kill pid={pid}: {e}")
    return killed


def _default_killer(pid: int) -> None:
    """Platform-aware process kill."""
    if os.name == "nt":
        os.system(f"taskkill /PID {pid} /F >nul 2>&1")
    else:
        import signal
        os.kill(pid, signal.SIGKILL)
