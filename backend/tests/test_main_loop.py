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


class _FakeConn:
    """Minimal stand-in for a psycopg2 connection: accepts autocommit
    assignment and close()."""
    def __init__(self):
        self.autocommit = False
    def close(self):
        pass


def test_run_once_calls_scanner_and_cleanup(monkeypatch):
    calls = []

    monkeypatch.setattr("watchdog.__main__.requeue_stalled", lambda conn: (calls.append("requeue"), 5)[1])
    monkeypatch.setattr("watchdog.__main__.cleanup_orphan_chromium", lambda **kw: (calls.append("cleanup"), 0)[1])
    monkeypatch.setattr("watchdog.__main__._connect", lambda: _FakeConn())

    run_once()

    assert calls == ["requeue", "cleanup"]
