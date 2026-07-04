"""Tests for reports metrics aggregation."""
import asyncio
import os
from datetime import datetime, timedelta

import psycopg2
import pytest

from services.reports_service import get_report_metrics


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_orders_for_reports(db_conn, monkeypatch):
    import services.reports_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS orders CASCADE")
    cur.execute("DROP TABLE IF EXISTS proposals CASCADE")
    cur.execute(
        """CREATE TABLE orders (
        id SERIAL PRIMARY KEY, client_id INTEGER, created_by INTEGER,
        order_number VARCHAR(100), name VARCHAR(500), qty INTEGER DEFAULT 1,
        total NUMERIC(14,2) DEFAULT 0, status VARCHAR(50) DEFAULT 'new',
        order_date VARCHAR(100), created_at VARCHAR(100), updated_at VARCHAR(100))"""
    )
    cur.execute(
        """CREATE TABLE proposals (
        id SERIAL PRIMARY KEY, client_id INTEGER, title VARCHAR(300),
        total_amount NUMERIC(14,2) DEFAULT 0, discount_global INTEGER DEFAULT 0,
        status VARCHAR(50) DEFAULT 'draft', email_sent BOOLEAN DEFAULT FALSE,
        created_at VARCHAR(100), updated_at VARCHAR(100))"""
    )
    now = datetime.now().isoformat()
    recent = (datetime.now() - timedelta(days=5)).isoformat()
    old = (datetime.now() - timedelta(days=100)).isoformat()
    # 2 delivered orders (revenue) + 1 cancelled (not revenue) + 1 old delivered (outside period)
    cur.execute(
        f"INSERT INTO orders (client_id, name, total, status, created_at) "
        f"VALUES (1,'A',50000,'delivered','{recent}')"
    )
    cur.execute(
        f"INSERT INTO orders (client_id, name, total, status, created_at) "
        f"VALUES (1,'B',30000,'delivered','{recent}')"
    )
    cur.execute(
        f"INSERT INTO orders (client_id, name, total, status, created_at) "
        f"VALUES (1,'C',10000,'cancelled','{recent}')"
    )
    cur.execute(
        f"INSERT INTO orders (client_id, name, total, status, created_at) "
        f"VALUES (1,'D',99999,'delivered','{old}')"
    )
    # 5 proposals, 2 delivered → conversion = 2/5 = 40%
    for i in range(5):
        cur.execute(
            f"INSERT INTO proposals (client_id, title, created_at) "
            f"VALUES (1,'KP{i}','{recent}')"
        )
    cur.close()

    TEST_DSN = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"
    )

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(svc, "get_db", _test_get_db)


def test_revenue_excludes_cancelled_and_old(seeded_orders_for_reports):
    m = _run(get_report_metrics(period="month"))
    # 50000 + 30000 = 80000 (cancelled excluded, old excluded)
    assert m["revenue"] == 80000.0
    assert m["order_count"] == 2  # 2 delivered in period


def test_avg_check(seeded_orders_for_reports):
    m = _run(get_report_metrics(period="month"))
    assert m["avg_check"] == 40000.0  # 80000 / 2


def test_conversion(seeded_orders_for_reports):
    m = _run(get_report_metrics(period="month"))
    assert m["proposals_count"] == 5
    assert m["delivered_count"] == 2
    assert m["conversion"] == 40.0  # 2/5*100


def test_dynamics_has_6_months(seeded_orders_for_reports):
    m = _run(get_report_metrics(period="month"))
    assert len(m["dynamics"]["labels"]) == 6
    assert len(m["dynamics"]["values"]) == 6
