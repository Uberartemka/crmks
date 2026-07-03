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
