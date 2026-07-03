from watchdog.config import TASK_TIMEOUTS, SCAN_INTERVAL_SECONDS, stall_timeout_for


def test_known_task_type_returns_its_timeout():
    assert stall_timeout_for("email_invoice") == 60
    assert stall_timeout_for("generate_pdf") == 600


def test_unknown_task_type_returns_default():
    assert stall_timeout_for("totally_new_task") == 300


def test_scan_interval_is_positive():
    assert SCAN_INTERVAL_SECONDS > 0
