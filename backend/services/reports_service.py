from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from db import get_db, q


def _period_range(period: str) -> tuple[str, str]:
    """Return (start_iso, end_iso) for the given period: week/month/quarter."""
    now = datetime.now()
    if period == "week":
        start = now - timedelta(days=7)
    elif period == "quarter":
        start = now - timedelta(days=90)
    else:  # month
        start = now - timedelta(days=30)
    return start.isoformat(), now.isoformat()


async def get_report_metrics(period: str = "month") -> Dict[str, Any]:
    """Compute real metrics from orders + proposals."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now()
    start, end = _period_range(period)

    # Revenue = sum of total from delivered/paid/shipped orders in period
    cursor.execute(
        q(
            """
        SELECT COALESCE(SUM(total), 0), COUNT(*)
        FROM orders
        WHERE status IN ('delivered', 'paid', 'shipped')
          AND created_at >= %s AND created_at <= %s
        """
        ),
        (start, end),
    )
    rev_row = cursor.fetchone()
    revenue = float(rev_row[0]) if rev_row and rev_row[0] is not None else 0.0
    order_count = int(rev_row[1]) if rev_row else 0

    # Average check = revenue / order_count
    avg_check = revenue / order_count if order_count > 0 else 0.0

    # KP conversion = delivered orders / total proposals in period
    cursor.execute(
        q(
            """
        SELECT COUNT(*) FROM proposals
        WHERE created_at >= %s AND created_at <= %s
        """
        ),
        (start, end),
    )
    proposals_count = cursor.fetchone()[0] or 0

    cursor.execute(
        q(
            """
        SELECT COUNT(*) FROM orders
        WHERE status = 'delivered'
          AND created_at >= %s AND created_at <= %s
        """
        ),
        (start, end),
    )
    delivered_count = cursor.fetchone()[0] or 0

    conversion = (delivered_count / proposals_count * 100) if proposals_count > 0 else 0.0

    # Monthly dynamics (last 6 months revenue)
    six_months_ago = (now - timedelta(days=180)).isoformat()
    cursor.execute(
        q(
            """
        SELECT created_at, total
        FROM orders
        WHERE status IN ('delivered', 'paid', 'shipped')
          AND created_at >= %s
        ORDER BY created_at ASC
        """
        ),
        (six_months_ago,),
    )
    rows = cursor.fetchall()
    conn.close()

    # Group by month (rolling 6-month window ending now)
    months: Dict[str, float] = {}
    month_labels = []
    for i in range(5, -1, -1):
        d = now - timedelta(days=i * 30)
        key = d.strftime("%Y-%m")
        label = d.strftime("%b")
        months[key] = 0.0
        month_labels.append(label)

    for row in rows:
        created = row[0] or ""
        total = float(row[1]) if row[1] else 0.0
        key = created[:7]  # YYYY-MM
        if key in months:
            months[key] += total

    dynamics = [round(months[k]) for k in sorted(months.keys())]

    return {
        "period": period,
        "revenue": round(revenue, 2),
        "order_count": order_count,
        "avg_check": round(avg_check, 2),
        "proposals_count": proposals_count,
        "delivered_count": delivered_count,
        "conversion": round(conversion, 1),
        "dynamics": {
            "labels": month_labels,
            "values": dynamics,
        },
    }
