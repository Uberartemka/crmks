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
