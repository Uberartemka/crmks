"""Tests for the new atomic _claim_next_task in QueueManager.

Verifies it respects process_after (deferred tasks not claimed) and uses
FOR UPDATE SKIP LOCKED semantics (only one claim per pending task).
"""
import datetime
import os

import psycopg2

# Force the QueueManager to talk to the test DB, not the dev DB.
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
)

from migrations.runner import apply_migration_001
from queue_manager import QueueManager


def _seed_pending(conn, *, task_type="email_invoice", process_after=None):
    cur = conn.cursor()
    if process_after is None:
        cur.execute(
            """
            INSERT INTO job_queue (task_type, status, payload, retries, max_retries,
                                   created_at, updated_at, claimed_at)
            VALUES (%s, 'pending', '{}', 0, 3, now(), now(), NULL)
            RETURNING id
            """,
            (task_type,),
        )
    else:
        cur.execute(
            """
            INSERT INTO job_queue (task_type, status, payload, retries, max_retries,
                                   created_at, updated_at, claimed_at, process_after)
            VALUES (%s, 'pending', '{}', 0, 3, now(), now(), NULL, %s)
            RETURNING id
            """,
            (task_type, process_after),
        )
    jid = cur.fetchone()[0]
    cur.close()
    return jid


def test_claim_picks_up_ready_task(db_conn):
    apply_migration_001(db_conn)
    jid = _seed_pending(db_conn)  # process_after NULL -> uses DEFAULT now()
    qm = QueueManager()
    claimed = qm._claim_next_task()
    assert claimed is not None
    assert claimed["id"] == jid
    assert claimed["type"] == "email_invoice"


def test_claim_skips_deferred_task(db_conn):
    apply_migration_001(db_conn)
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=300)
    _seed_pending(db_conn, process_after=future)
    qm = QueueManager()
    claimed = qm._claim_next_task()
    assert claimed is None  # nothing claimable yet


def test_claim_sets_processing_and_claimed_at(db_conn):
    apply_migration_001(db_conn)
    jid = _seed_pending(db_conn)
    qm = QueueManager()
    qm._claim_next_task()

    cur = db_conn.cursor()
    cur.execute("SELECT status, claimed_at FROM job_queue WHERE id = %s", (jid,))
    status, claimed_at = cur.fetchone()
    cur.close()
    assert status == "processing"
    assert claimed_at is not None
