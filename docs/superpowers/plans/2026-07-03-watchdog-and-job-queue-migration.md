# Watchdog + job_queue Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone watchdog process that requeues stalled `job_queue` tasks and applies exponential backoff on retries, plus the migration that makes this possible.

**Architecture:** The watchdog runs as a separate `python -m watchdog` process under systemd, independent of the FastAPI app and the queue worker. It scans `job_queue` every 60 seconds using sync psycopg2 (same access pattern as the existing `QueueManager`). Per-`task_type` stall timeouts live in a code dict. The migration adds `claimed_at`, `process_after` columns and converts the `varchar` timestamps to `timestamptz`. The existing `QueueManager` is adapted to use the new atomic claim (`FOR UPDATE SKIP LOCKED` + `process_after` filter) and to set `process_after` into the future on failure (exponential backoff + jitter).

**Tech Stack:** Python 3.14, psycopg2, PostgreSQL, pytest (sync), systemd.

**Reference spec:** `docs/superpowers/specs/2026-07-03-multitenancy-and-scalability-design.md`, Section 3 (Watchdog).

---

## File Structure

**Create:**
- `backend/requirements.txt` — append `pytest` (modify)
- `backend/pytest.ini` — pytest config
- `backend/tests/__init__.py` — package marker
- `backend/tests/conftest.py` — DB fixtures, test-DB bootstrap
- `backend/migrations/__init__.py` — package marker
- `backend/migrations/001_job_queue_watchdog.sql` — idempotent migration
- `backend/migrations/runner.py` — idempotent migration runner
- `backend/watchdog/__init__.py` — package marker
- `backend/watchdog/config.py` — `TASK_TIMEOUTS`, scan interval
- `backend/watchdog/scanner.py` — `requeue_stalled`, `cleanup_orphan_chromium`
- `backend/watchdog/__main__.py` — `python -m watchdog` entry loop
- `deploy/watchdog.service` — systemd unit

**Modify:**
- `backend/queue_manager.py` — atomic claim, backoff on failure
- `backend/main.py` — apply migrations on startup

**Responsibilities:**
- `migrations/runner.py` — only applies idempotent SQL files; no business logic.
- `watchdog/scanner.py` — pure DB operations for requeue + cleanup; no loop, no process management. Easy to unit-test.
- `watchdog/__main__.py` — the loop + logging + signal handling. Calls into `scanner`.
- `watchdog/config.py` — constants only, no imports from app.

---

## Prerequisites (do once before starting)

You need a throwaway Postgres database for tests. Create it now:

```
psql -U postgres -h localhost -c "CREATE DATABASE hhb_b2b_test;"
```

If `psql` is not on PATH (Windows), use the pgAdmin query tool or:
```
python -c "import psycopg2; c=psycopg2.connect('postgresql://postgres:235813@localhost:5432/postgres'); c.autocommit=True; c.cursor().execute('CREATE DATABASE hhb_b2b_test'); print('ok')"
```

Set the test DB URL (used by `conftest.py`):
```
set TEST_DATABASE_URL=postgresql://postgres:235813@localhost:5432/hhb_b2b_test
```

---

## Task 1: Test infrastructure

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Add pytest to requirements**

Append to `backend/requirements.txt` (keep existing lines):

```
pytest>=8.0.0
```

- [ ] **Step 2: Create pytest config**

Create `backend/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
```

- [ ] **Step 3: Create tests package marker**

Create `backend/tests/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Write conftest with DB fixture (failing test first)**

Create `backend/tests/conftest.py`:

```python
"""Shared pytest fixtures. Tests run against a real PostgreSQL test DB.

Requires env var TEST_DATABASE_URL pointing at a throwaway database.
The fixture resets the schema between tests by truncating known tables.
"""
import os
import pytest
import psycopg2

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
)

# Tables that the watchdog/migration tests touch. Truncated before each test.
_TABLES_TO_CLEAR = ["job_queue"]


def _connect():
    return psycopg2.connect(TEST_DATABASE_URL)


@pytest.fixture
def db_conn():
    """Yield a raw psycopg2 connection to the test DB.

    Each test starts with job_queue empty. Schema (job_queue table) must be
    created by the migration-test setup or by running migrations first.
    """
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    for t in _TABLES_TO_CLEAR:
        cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
    cur.close()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def test_db_url():
    return TEST_DATABASE_URL
```

- [ ] **Step 5: Verify conftest loads**

Run from `backend/`:

```
python -m pytest --collect-only
```

Expected: `collected 0 items` and no errors (no ImportError). If `TEST_DATABASE_URL` is unreachable you will only see errors once a test actually uses `db_conn`.

- [ ] **Step 6: Commit**

```
git add backend/requirements.txt backend/pytest.ini backend/tests/
git commit -m "test: add pytest infrastructure with Postgres DB fixtures"
```

---

## Task 2: Idempotent migration SQL

**Files:**
- Create: `backend/migrations/__init__.py`
- Create: `backend/migrations/001_job_queue_watchdog.sql`
- Test: `backend/tests/test_migration_001.py`

- [ ] **Step 1: Create migrations package marker**

Create `backend/migrations/__init__.py` (empty):

```python
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_migration_001.py`:

```python
"""Verify migration 001 adds watchdog columns and converts timestamps.

Runs against TEST_DATABASE_URL. The fixture creates a 'legacy' job_queue
schema first, then applies the migration, then asserts the new shape.
"""
import datetime
import psycopg2
import pytest

from migrations.runner import apply_migration_001


@pytest.fixture
def legacy_job_queue(db_conn):
    """Recreate job_queue in its pre-migration shape."""
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS job_queue")
    cur.execute(
        """
        CREATE TABLE job_queue (
            id SERIAL PRIMARY KEY,
            task_type VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            payload TEXT NOT NULL,
            retries INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT,
            created_at VARCHAR(100) NOT NULL,
            updated_at VARCHAR(100) NOT NULL
        )
        """
    )
    cur.close()
    return db_conn


def _column_type(conn, table, column):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def test_migration_adds_claimed_at(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "claimed_at") == "timestamp with time zone"


def test_migration_adds_process_after(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "process_after") == "timestamp with time zone"


def test_migration_converts_created_at_to_timestamptz(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "created_at") == "timestamp with time zone"


def test_migration_converts_updated_at_to_timestamptz(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    assert _column_type(legacy_job_queue, "job_queue", "updated_at") == "timestamp with time zone"


def test_migration_is_idempotent(legacy_job_queue):
    apply_migration_001(legacy_job_queue)
    apply_migration_001(legacy_job_queue)  # second run must not raise
    assert _column_type(legacy_job_queue, "job_queue", "claimed_at") == "timestamp with time zone"
```

- [ ] **Step 3: Run test to verify it fails**

```
python -m pytest tests/test_migration_001.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'migrations.runner'` (or import error). This confirms the test runs and the production code is missing.

- [ ] **Step 4: Create the migration SQL file**

Create `backend/migrations/001_job_queue_watchdog.sql`:

```sql
-- Migration 001: watchdog support for job_queue
-- Idempotent: each statement guards on existence before altering.
-- Converts varchar timestamps to timestamptz, adds claimed_at / process_after.

-- 1. Add claimed_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'claimed_at'
    ) THEN
        ALTER TABLE job_queue ADD COLUMN claimed_at timestamptz;
    END IF;
END $$;

-- 2. Add process_after (default now so existing rows are immediately claimable)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'process_after'
    ) THEN
        ALTER TABLE job_queue ADD COLUMN process_after timestamptz NOT NULL DEFAULT now();
    END IF;
END $$;

-- 3. Convert created_at varchar -> timestamptz
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'created_at'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE job_queue ALTER COLUMN created_at TYPE timestamptz
            USING created_at::timestamptz;
        ALTER TABLE job_queue ALTER COLUMN created_at SET DEFAULT now();
    END IF;
END $$;

-- 4. Convert updated_at varchar -> timestamptz
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_queue' AND column_name = 'updated_at'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE job_queue ALTER COLUMN updated_at TYPE timestamptz
            USING updated_at::timestamptz;
        ALTER TABLE job_queue ALTER COLUMN updated_at SET DEFAULT now();
    END IF;
END $$;

-- 5. Partial index for watchdog + worker claims
CREATE INDEX IF NOT EXISTS idx_job_queue_claim
    ON job_queue (status, process_after)
    WHERE status IN ('pending', 'processing');
```

- [ ] **Step 5: Implement the runner**

Create `backend/migrations/runner.py`:

```python
"""Idempotent migration runner.

Applies numbered .sql files in order. Each migration is applied inside its
own transaction. No bookkeeping table (YAGNI for now): idempotency is
guaranteed by the SQL itself (every ALTER is guarded by information_schema
checks), so re-running is safe.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger("HHB_B2B")

_MIGRATIONS_DIR = Path(__file__).parent


def apply_migration_001(conn) -> None:
    """Apply migration 001 to a *raw* psycopg2 connection.

    `conn` must be a sync psycopg2 connection; autocommit is set inside.
    """
    sql_path = _MIGRATIONS_DIR / "001_job_queue_watchdog.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 001_job_queue_watchdog.sql applied.")


def apply_all(dsn: str) -> None:
    """Apply all migrations to the DB at `dsn`. Used on app startup."""
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        apply_migration_001(conn)
    finally:
        conn.close()
```

- [ ] **Step 6: Run tests to verify they pass**

```
python -m pytest tests/test_migration_001.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```
git add backend/migrations/ backend/tests/test_migration_001.py
git commit -m "feat(db): add idempotent job_queue watchdog migration"
```

---

## Task 3: Apply migrations on app startup

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Read current startup to find insertion point**

Open `backend/main.py`. Locate the `on_startup()` coroutine (around line 17):

```python
async def on_startup() -> None:
    startup_init_db()
    # _init_queue_manager()  # disabled on Railway ...
    await init_async_pool()
    await init_token_store()
```

- [ ] **Step 2: Add migration import**

In the imports block (after the `from db_async import ...` line), add:

```python
from migrations.runner import apply_all
from db import PG_URL
```

- [ ] **Step 3: Call apply_all() first in on_startup**

Replace the `on_startup` body so migrations run before the async pool starts:

```python
async def on_startup() -> None:
    startup_init_db()
    # Apply DB migrations (idempotent) before any pool relies on the schema.
    apply_all(PG_URL)
    # _init_queue_manager()  # disabled on Railway — queue requires PostgreSQL + Chromium
    await init_async_pool()
    await init_token_store()
```

- [ ] **Step 4: Smoke-test the startup path**

Run a quick import + function call (does not start the server):

```
python -c "import asyncio; from main import on_startup; asyncio.run(on_startup()); print('startup ok')"
```

Expected: prints `startup ok` with no traceback. You should see `[migration] 001_job_queue_watchdog.sql applied.` in logs.

If the dev DB `hhb_b2b` does not yet have a `job_queue` table, the migration's `ALTER` guards will no-op safely; create the table first via `schema.sql` if missing.

- [ ] **Step 5: Commit**

```
git add backend/main.py
git commit -m "feat(startup): apply DB migrations on app startup"
```

---

## Task 4: Watchdog config

**Files:**
- Create: `backend/watchdog/__init__.py`
- Create: `backend/watchdog/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Create watchdog package marker**

Create `backend/watchdog/__init__.py`:

```python
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_config.py`:

```python
from watchdog.config import TASK_TIMEOUTS, SCAN_INTERVAL_SECONDS, stall_timeout_for


def test_known_task_type_returns_its_timeout():
    assert stall_timeout_for("email_invoice") == 60
    assert stall_timeout_for("generate_pdf") == 600


def test_unknown_task_type_returns_default():
    assert stall_timeout_for("totally_new_task") == 300


def test_scan_interval_is_positive():
    assert SCAN_INTERVAL_SECONDS > 0
```

- [ ] **Step 3: Run test to verify it fails**

```
python -m pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'watchdog.config'`.

- [ ] **Step 4: Implement config**

Create `backend/watchdog/config.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```
git add backend/watchdog/__init__.py backend/watchdog/config.py backend/tests/test_config.py
git commit -m "feat(watchdog): add per-task-type stall timeout config"
```

---

## Task 5: Watchdog scanner — requeue stalled tasks

**Files:**
- Create: `backend/watchdog/scanner.py`
- Test: `backend/tests/test_scanner_requeue.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scanner_requeue.py`:

```python
"""Tests for watchdog.scanner.requeue_stalled.

Each test seeds a job_queue row in a specific (status, age, task_type)
state, runs requeue_stalled, and asserts the resulting status.
"""
import datetime

import psycopg2

from migrations.runner import apply_migration_001
from watchdog.scanner import requeue_stalled


def _insert_job(conn, *, task_type, status, claimed_at, process_after=None, retries=0):
    cur = conn.cursor()
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_scanner_requeue.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'watchdog.scanner'`.

- [ ] **Step 3: Implement requeue_stalled**

Create `backend/watchdog/scanner.py`:

```python
"""Watchdog DB operations. No loop, no process management — just the SQL.

Each function takes a *raw sync psycopg2 connection* (autocommit=True) and
returns a count of affected rows. Keeps the loop logic in __main__ testable.
"""
import logging

from watchdog.config import TASK_TIMEOUTS

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
    from watchdog.config import DEFAULT_STALL_TIMEOUT
    cur = conn.cursor()
    try:
        # Exclude task types that already have an explicit timeout above.
        excluded = tuple(TASK_TIMEOUTS.keys())
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_scanner_requeue.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add backend/watchdog/scanner.py backend/tests/test_scanner_requeue.py
git commit -m "feat(watchdog): requeue stalled tasks with per-type timeouts"
```

---

## Task 6: Orphan Chromium cleanup

**Files:**
- Modify: `backend/watchdog/scanner.py`
- Test: `backend/tests/test_chromium_cleanup.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_chromium_cleanup.py`:

```python
"""Tests for cleanup_orphan_chromium.

We cannot spawn real orphan Chromium in CI, so cleanup_orphan_chromium takes
a *killer* callable that it calls with each detected PID. The test injects a
fake lister + killer and asserts the killer is invoked correctly.
"""
from watchdog.scanner import cleanup_orphan_chromium


def test_killer_called_for_each_old_chromium_pid(monkeypatch):
    # Fake: two chromium processes older than the threshold
    monkeypatch.setattr(
        "watchdog.scanner._list_chromium_procs",
        lambda older_than_sec=300: [
            (11111, "chromium", 600),
            (22222, "chrome-headless", 400),
        ],
    )
    killed = []
    cleanup_orphan_chromium(older_than_sec=300, killer=lambda pid: killed.append(pid))
    assert killed == [11111, 22222]


def test_young_processes_are_not_killed(monkeypatch):
    monkeypatch.setattr(
        "watchdog.scanner._list_chromium_procs",
        lambda older_than_sec=300: [(11111, "chromium", 60)],  # only 60s old
    )
    killed = []
    cleanup_orphan_chromium(older_than_sec=300, killer=lambda pid: killed.append(pid))
    assert killed == []


def test_no_chromium_returns_zero(monkeypatch):
    monkeypatch.setattr("watchdog.scanner._list_chromium_procs", lambda older_than_sec=300: [])
    killed = []
    result = cleanup_orphan_chromium(older_than_sec=300, killer=lambda pid: killed.append(pid))
    assert result == 0
    assert killed == []
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_chromium_cleanup.py -v
```

Expected: FAIL with `ImportError: cannot import name 'cleanup_orphan_chromium'`.

- [ ] **Step 3: Implement cleanup_orphan_chromium**

Append to `backend/watchdog/scanner.py`:

```python
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
```

- [ ] **Step 4: Add psutil to requirements**

Append to `backend/requirements.txt`:

```
psutil>=5.9.0
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_chromium_cleanup.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```
git add backend/watchdog/scanner.py backend/tests/test_chromium_cleanup.py backend/requirements.txt
git commit -m "feat(watchdog): cleanup orphan chromium processes older than threshold"
```

---

## Task 7: Watchdog entry loop

**Files:**
- Create: `backend/watchdog/__main__.py`
- Test: `backend/tests/test_main_loop.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_main_loop.py`:

```python
"""Tests for the watchdog run-once entrypoint.

We don't test the infinite loop; we test run_once (one scan iteration) and
the backoff calculation helper.
"""
from watchdog.__main__ import run_once, compute_backoff_seconds


def test_backoff_grows_exponentially():
    # attempt 1 -> ~2s, attempt 2 -> ~4s, attempt 3 -> ~8s (before jitter)
    for attempt, expected_min in [(1, 2), (2, 4), (3, 8), (6, 64)]:
        secs = compute_backoff_seconds(attempt)
        # jitter multiplies by (1+random) in [1,2), so range is [base, 2*base)
        assert expected_min <= secs < expected_min * 2, f"attempt {attempt}: got {secs}"


def test_backoff_caps_at_attempt_6():
    # attempts beyond 6 must not exceed the attempt-6 range
    big = compute_backoff_seconds(20)
    assert big < 64 * 2


def test_run_once_calls_scanner_and_cleanup(monkeypatch):
    calls = []

    monkeypatch.setattr("watchdog.__main__.requeue_stalled", lambda conn: (calls.append("requeue"), 5)[1])
    monkeypatch.setattr("watchdog.__main__.cleanup_orphan_chromium", lambda **kw: (calls.append("cleanup"), 0)[1])
    monkeypatch.setattr("watchdog.__main__._connect", lambda: object())  # fake conn

    run_once()

    assert calls == ["requeue", "cleanup"]
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_main_loop.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'watchdog.__main__'`.

- [ ] **Step 3: Implement __main__.py**

Create `backend/watchdog/__main__.py`:

```python
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
import sys
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
    """One scan iteration. Returns total requeued count via logs."""
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
    logger.info(f"[watchdog] starting. Scan every {SCAN_INTERVAL_SECONDS}s. DB={DATABASE_URL.split('@')[-1]}")
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_main_loop.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Smoke-test the module boots**

```
python -c "from watchdog.__main__ import main, run_once, compute_backoff_seconds; print('import ok')"
```

Expected: prints `import ok`.

- [ ] **Step 6: Commit**

```
git add backend/watchdog/__main__.py backend/tests/test_main_loop.py
git commit -m "feat(watchdog): add main loop with backoff helper and signal handling"
```

---

## Task 8: Adapt QueueManager — atomic claim

**Files:**
- Modify: `backend/queue_manager.py` (`_claim_next_task`)
- Test: `backend/tests/test_queue_claim.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_queue_claim.py`:

```python
"""Tests for the new atomic _claim_next_task in QueueManager.

Verifies it respects process_after (deferred tasks not claimed) and uses
FOR UPDATE SKIP LOCKED semantics (only one claim per pending task).
"""
import datetime

from migrations.runner import apply_migration_001
from queue_manager import QueueManager


def _seed_pending(conn, *, task_type="email_invoice", process_after=None):
    cur = conn.cursor()
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
    jid = _seed_pending(db_conn)  # process_after NULL -> claimable
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_queue_claim.py -v
```

Expected: FAIL — the current `_claim_next_task` does not respect `process_after` and uses the python `threading.Lock` pattern. Tests for deferred-task skipping will fail.

- [ ] **Step 3: Replace _claim_next_task with the atomic version**

In `backend/queue_manager.py`, replace the entire `_claim_next_task` method (currently lines ~197–230) with:

```python
    def _claim_next_task(self):
        """Atomically claim the next eligible pending task.

        Uses FOR UPDATE SKIP LOCKED so multiple workers (or a worker + tests)
        cannot grab the same row. Respects process_after: a task whose
        process_after is in the future (deferred for backoff) is skipped.
        No python-level lock — Postgres row locking is the source of truth.
        """
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_queue
                   SET status = 'processing',
                       claimed_at = now(),
                       updated_at = now(),
                       retries = retries + 1
                 WHERE id = (
                   SELECT id FROM job_queue
                    WHERE status = 'pending'
                      AND process_after <= now()
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                 )
                 RETURNING id, task_type, payload, retries, max_retries
                """
            )
            row = cursor.fetchone()
            conn.commit()
            if row:
                task_id, task_type, payload, retries, max_retries = row
                return {
                    "id": task_id,
                    "type": task_type,
                    "payload": json.loads(payload),
                    "retries": retries,
                    "max_retries": max_retries,
                }
            return None
        finally:
            conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_queue_claim.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full test suite to check nothing regressed**

```
python -m pytest -v
```

Expected: all tests pass (migration, config, scanner, claim, chromium, main loop).

- [ ] **Step 6: Commit**

```
git add backend/queue_manager.py backend/tests/test_queue_claim.py
git commit -m "feat(queue): atomic claim with process_after filter, drop python lock"
```

---

## Task 9: Apply backoff on failure in QueueManager

**Files:**
- Modify: `backend/queue_manager.py` (`_process_task` failure branch)
- Test: `backend/tests/test_queue_backoff.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_queue_backoff.py`:

```python
"""Verify a failed task gets process_after pushed into the future (backoff)."""
import datetime

from migrations.runner import apply_migration_001
from queue_manager import QueueManager


def test_failed_task_gets_future_process_after(db_conn, monkeypatch):
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
    # Force the failure path: unknown task type raises, but we have a known type.
    # Instead, call the internal failure handler directly.
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
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_queue_backoff.py -v
```

Expected: FAIL with `AttributeError: 'QueueManager' object has no attribute '_mark_failed'`.

- [ ] **Step 3: Extract _mark_failed with backoff**

In `backend/queue_manager.py`, add this import near the top (after `import threading`):

```python
import random
```

Then add a new method to the `QueueManager` class (place it just before `_process_task`):

```python
    def _mark_failed(self, task_id, error_msg, retries, max_retries):
        """Handle a failed task: either requeue with backoff or mark 'failed'.

        Backoff: process_after = now + 2^min(retries,6) * (1+jitter) seconds.
        """
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cursor = conn.cursor()
            if retries >= max_retries:
                cursor.execute(
                    """
                    UPDATE job_queue
                       SET status = 'failed', error_message = %s, updated_at = now()
                     WHERE id = %s
                    """,
                    (error_msg, task_id),
                )
                logger.error(f"[!] [Queue Worker] Task #{task_id} exhausted retries. Status: FAILED")
            else:
                backoff = (2 ** min(retries, 6)) * (1 + random.random())
                cursor.execute(
                    """
                    UPDATE job_queue
                       SET status = 'pending',
                           error_message = %s,
                           process_after = now() + (%s || ' seconds')::interval,
                           claimed_at = NULL,
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (error_msg, str(backoff), task_id),
                )
                logger.warning(
                    f"[*] [Queue Worker] Task #{task_id} returned to queue. "
                    f"Retry in {backoff:.1f}s (attempt {retries}/{max_retries})"
                )
            conn.commit()
        finally:
            conn.close()
```

- [ ] **Step 4: Replace the failure branch in _process_task**

In `_process_task`, find the existing failure-handling block that begins after `now = datetime.now().isoformat()` and the `with self.lock:` context. Replace the entire `if success: ... else: ...` block (the part starting at `if success:`) with:

```python
        if success:
            conn = psycopg2.connect(DATABASE_URL)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE job_queue SET status = 'completed', updated_at = now() WHERE id = %s",
                    (task_id,),
                )
                conn.commit()
            finally:
                conn.close()
            logger.info(f"[Queue Worker] Task #{task_id} completed successfully!")
        else:
            self._mark_failed(task_id, error_msg, task["retries"], task["max_retries"])
```

This delegates to `_mark_failed`, which applies backoff. Note the old `now = datetime.now().isoformat()` line and the `with self.lock:` wrapper are removed — `_mark_failed` manages its own connection and `now()` is computed server-side.

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_queue_backoff.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run the full suite**

```
python -m pytest -v
```

Expected: all green.

- [ ] **Step 7: Commit**

```
git add backend/queue_manager.py backend/tests/test_queue_backoff.py
git commit -m "feat(queue): exponential backoff with jitter on task failure"
```

---

## Task 10: systemd unit + deploy doc

**Files:**
- Create: `deploy/watchdog.service`
- Create: `deploy/watchdog.md`

- [ ] **Step 1: Create the systemd unit**

Create `deploy/watchdog.service`:

```ini
[Unit]
Description=frontcrm job_queue watchdog
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/frontcrm/backend
EnvironmentFile=/var/www/frontcrm/backend/.env
ExecStart=/var/www/frontcrm/backend/venv/bin/python -m watchdog
Restart=always
RestartSec=10

# Hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/var/www/frontcrm/backend
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

> Adjust paths/user to match the actual server layout. The `ReadWritePaths`
> line lets the process write its own log/runtime files; nothing else.

- [ ] **Step 2: Create the deploy doc**

Create `deploy/watchdog.md`:

```markdown
# Watchdog deployment

The watchdog is a standalone process that requeues stalled `job_queue` tasks
and cleans up orphan Chromium processes. It must run as its own service,
independent of the FastAPI app and the queue worker.

## Install

```bash
# 1. Copy the unit file
sudo cp deploy/watchdog.service /etc/systemd/system/

# 2. Adjust paths inside the unit if your layout differs
sudo nano /etc/systemd/system/watchdog.service

# 3. Reload systemd and enable
sudo systemctl daemon-reload
sudo systemctl enable --now watchdog

# 4. Verify
sudo systemctl status watchdog
sudo journalctl -u watchdog -f
```

## Operation

- **Scan interval:** 60 s (see `backend/watchdog/config.py`).
- **Stall timeouts:** per task_type — `email_invoice`/`crm_lead` 60 s,
  `1c_sync`/`generate_pdf` 600 s.
- **Backoff:** failed tasks are deferred by `2^attempt × (1+jitter)` seconds,
  capped at attempt 6.

## Restart behaviour

`Restart=always` with `RestartSec=10`: if the watchdog crashes, systemd
brings it back in 10 s. A stuck scan does not affect the FastAPI app or the
queue worker — they continue independently.

## Why a separate process

- If the queue worker dies, the watchdog still requeues its in-flight tasks.
- If the FastAPI app is redeployed, the watchdog keeps running.
- One watchdog per cluster — do NOT run multiple instances, or tasks may be
  requeued redundantly. The unit file enforces a single instance.
```

- [ ] **Step 3: Commit**

```
git add deploy/watchdog.service deploy/watchdog.md
git commit -m "deploy: add watchdog systemd unit and runbook"
```

---

## Task 11: Full-suite verification + manual smoke

- [ ] **Step 1: Run the complete test suite**

```
cd backend
python -m pytest -v
```

Expected: all tests pass. Approximate count: 3 (config) + 4 (requeue) + 3 (chromium) + 3 (main loop) + 5 (migration) + 3 (claim) + 2 (backoff) = ~23 tests.

- [ ] **Step 2: Manual smoke: start the watchdog against the dev DB**

In one terminal:

```
cd backend
python -m watchdog
```

Expected output every 60 s:
```
[watchdog] scan complete: no stalled tasks.
```

- [ ] **Step 3: Manual smoke: simulate a stall**

In a second terminal, insert a fake stalled task:

```
python -c "import psycopg2, datetime; c=psycopg2.connect('postgresql://postgres:235813@localhost:5432/hhb_b2b'); c.autocommit=True; cur=c.cursor(); cur.execute(\"INSERT INTO job_queue (task_type, status, payload, retries, max_retries, created_at, updated_at, claimed_at, process_after) VALUES ('email_invoice', 'processing', '{}', 1, 3, now(), now(), now() - interval '5 minutes', now())\"); print('seeded')"
```

Wait up to 60 s. Expected in the watchdog terminal:
```
[watchdog] requeued 1 stalled task(s).
[watchdog] scan complete: 1 task(s) requeued.
```

- [ ] **Step 4: Verify the requeued task is pending again**

```
python -c "import psycopg2; c=psycopg2.connect('postgresql://postgres:235813@localhost:5432/hhb_b2b'); cur=c.cursor(); cur.execute(\"SELECT id, status, error_message FROM job_queue WHERE task_type='email_invoice' ORDER BY id DESC LIMIT 1\"); print(cur.fetchone())"
```

Expected: status `pending`, error_message contains `[watchdog] requeued after stall`.

- [ ] **Step 5: Stop the watchdog (Ctrl+C)**

Expected: `[watchdog] received signal 2, stopping after current scan.` then `[watchdog] stopped.`

- [ ] **Step 6: Final commit (if any uncommitted doc tweaks)**

```
git status
# if clean, nothing to commit — done
```

---

## Done criteria

- [ ] All pytest tests pass (~23 tests)
- [ ] Migration applied to dev DB (`hhb_b2b`) without error
- [ ] App starts (`on_startup` runs migrations)
- [ ] `python -m watchdog` runs and scans every 60 s
- [ ] Simulated stalled task gets requeued with a `[watchdog]` note
- [ ] `deploy/watchdog.service` exists and is documented
- [ ] No `_tmp_*` test scaffolding committed; only `tests/` directory

## Out of scope (handled in later plans)

- Redis-backed queue (ARQ/RQ) — Plan 4
- Multi-tenancy (`tenants`, RLS, tenant middleware) — Plan 2
- Custom fields — Plan 3
- pgbouncer, process-model split, `/health`+`/ready` — Plan 5
- The watchdog itself stays when Plan 4 lands — only the queue worker changes
