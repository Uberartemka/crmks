"""Verify a failed task gets process_after pushed into the future (backoff)."""
import datetime
import os

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
)

from migrations.runner import apply_migration_001
from queue_manager import QueueManager


def test_failed_task_gets_future_process_after(db_conn):
    apply_migration_001(db_conn)
    # Seed a task that is already claimed, retries=1, about to fail
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO job_queue (task_type, status, payload, retries, max_retries,
                               created_at, updated_at, claimed_at, process_after, error_message)
        VALUES ('crm_lead', 'processing', '{}', 1, 3, now(), now(), now(), now(), NULL)
        RETURNING id
        """
    )
    jid = cur.fetchone()[0]
    cur.close()

    qm = QueueManager()
    # Call the internal failure handler directly.
    qm._mark_failed(jid, error_msg="simulated", retries=1, max_retries=3)

    cur = db_conn.cursor()
    cur.execute("SELECT status, process_after FROM job_queue WHERE id = %s", (jid,))
    status, process_after = cur.fetchone()
    cur.close()
    assert status == "pending"  # not exhausted retries yet
    assert process_after > datetime.datetime.now(datetime.timezone.utc)


def test_failed_task_exhausting_retries_goes_to_failed(db_conn):
    apply_migration_001(db_conn)
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO job_queue (task_type, status, payload, retries, max_retries,
                               created_at, updated_at, claimed_at, process_after)
        VALUES ('crm_lead', 'processing', '{}', 3, 3, now(), now(), now(), now())
        RETURNING id
        """
    )
    jid = cur.fetchone()[0]
    cur.close()

    qm = QueueManager()
    qm._mark_failed(jid, error_msg="simulated", retries=3, max_retries=3)

    cur = db_conn.cursor()
    cur.execute("SELECT status FROM job_queue WHERE id = %s", (jid,))
    status = cur.fetchone()[0]
    cur.close()
    assert status == "failed"
