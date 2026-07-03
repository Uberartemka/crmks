"""Tests for watchdog.scanner.requeue_stalled.

Each test seeds a job_queue row in a specific (status, age, task_type)
state, runs requeue_stalled, and asserts the resulting status.
"""
import datetime

from migrations.runner import apply_migration_001
from watchdog.scanner import requeue_stalled


def _insert_job(conn, *, task_type, status, claimed_at, process_after=None, retries=0):
    cur = conn.cursor()
    # process_after: if None, leave it to the column DEFAULT now(); otherwise
    # bind a real timestamp value. Kept parameterised (no SQL interpolation).
    if process_after is None:
        cur.execute(
            """
            INSERT INTO job_queue (task_type, status, payload, retries, max_retries,
                                   created_at, updated_at, claimed_at)
            VALUES (%s, %s, %s, %s, 3, now(), now(), %s)
            RETURNING id
            """,
            (task_type, status, "{}", retries, claimed_at),
        )
    else:
        cur.execute(
            """
            INSERT INTO job_queue (task_type, status, payload, retries, max_retries,
                                   created_at, updated_at, claimed_at, process_after)
            VALUES (%s, %s, %s, %s, 3, now(), now(), %s, %s)
            RETURNING id
            """,
            (task_type, status, "{}", retries, claimed_at, process_after),
        )
    job_id = cur.fetchone()[0]
    cur.close()
    return job_id


def _job_status(conn, job_id):
    cur = conn.cursor()
    cur.execute("SELECT status FROM job_queue WHERE id = %s", (job_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def test_stalled_email_job_is_requeued(db_conn):
    apply_migration_001(db_conn)
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120)
    jid = _insert_job(db_conn, task_type="email_invoice", status="processing", claimed_at=old)

    requeued = requeue_stalled(db_conn)

    assert requeued == 1
    assert _job_status(db_conn, jid) == "pending"


def test_fresh_email_job_is_not_touched(db_conn):
    apply_migration_001(db_conn)
    recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)
    jid = _insert_job(db_conn, task_type="email_invoice", status="processing", claimed_at=recent)

    requeued = requeue_stalled(db_conn)

    assert requeued == 0
    assert _job_status(db_conn, jid) == "processing"


def test_pdf_job_uses_longer_timeout(db_conn):
    apply_migration_001(db_conn)
    # 3 minutes old — would be stalled under the 60s rule, but PDF gets 600s
    age = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=180)
    jid = _insert_job(db_conn, task_type="generate_pdf", status="processing", claimed_at=age)

    requeued = requeue_stalled(db_conn)

    assert requeued == 0
    assert _job_status(db_conn, jid) == "processing"


def test_requeued_job_records_watchdog_note(db_conn):
    apply_migration_001(db_conn)
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120)
    jid = _insert_job(db_conn, task_type="crm_lead", status="processing", claimed_at=old)

    requeue_stalled(db_conn)

    cur = db_conn.cursor()
    cur.execute("SELECT error_message, claimed_at FROM job_queue WHERE id = %s", (jid,))
    err, claimed_at = cur.fetchone()
    cur.close()
    assert err is not None and "watchdog" in err
    assert claimed_at is None
