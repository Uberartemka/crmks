from __future__ import annotations

from datetime import datetime

from db import get_db, q


def recalc_proposal_total(proposal_id: int) -> None:
    """
    Recalculate total amount for a proposal based on its items.
    Applies item discount first, then global discount.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(q("SELECT discount_global FROM proposals WHERE id = %s"), (proposal_id,))
        row = cursor.fetchone()
        if not row:
            return

        global_discount = row[0]

        cursor.execute(
            q("""
                SELECT qty, price_base, discount_item
                FROM proposal_items
                WHERE proposal_id = %s
            """),
            (proposal_id,),
        )

        total = 0.0
        for qty, price_base, discount_item in cursor.fetchall():
            price_after_item = float(price_base) * (1 - int(discount_item) / 100)
            price_after_global = price_after_item * (1 - int(global_discount) / 100)
            total += price_after_global * int(qty)

        cursor.execute(
            q(
                "UPDATE proposals SET total_amount = %s, updated_at = %s WHERE id = %s"
            ),
            (total, datetime.now().isoformat(), proposal_id),
        )

        conn.commit()
    finally:
        conn.close()
