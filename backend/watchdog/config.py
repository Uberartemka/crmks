"""Watchdog configuration constants.

Stall timeouts are per task_type, in seconds. A task that has been in
'processing' longer than its timeout is considered stalled and is returned
to 'pending' by the watchdog.

These are *config*, not data: identical for all tenants and not user-editable.
If per-tenant overrides become necessary later, move them to tenants.settings
jsonb (YAGNI for now).
"""

# Seconds between watchdog scans of job_queue.
SCAN_INTERVAL_SECONDS = 60

# Per task_type stall timeout (seconds). Mirrors the task types handled by
# QueueManager._process_task in queue_manager.py.
TASK_TIMEOUTS = {
    "email_invoice": 60,
    "crm_lead": 60,
    "1c_sync": 600,        # 10 min — 1C inventory sync can be slow
    "generate_pdf": 600,   # 10 min — Playwright/Chromium is slow
}

# Fallback for task types not listed above.
DEFAULT_STALL_TIMEOUT = 300  # 5 min


def stall_timeout_for(task_type: str) -> int:
    """Return the stall timeout in seconds for a task_type."""
    return TASK_TIMEOUTS.get(task_type, DEFAULT_STALL_TIMEOUT)
