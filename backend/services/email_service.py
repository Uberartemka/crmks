from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from db import get_db, q
from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))


def _get_proposal_for_email(proposal_id: int) -> dict[str, Any]:
    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute(
            q(
                """
                SELECT p.id, p.title, p.total_amount, p.discount_global, p.created_at,
                       c.name AS client_name
                FROM proposals p
                JOIN clients c ON p.client_id = c.id
                WHERE p.id = %s
                """
            ),
            (proposal_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Proposal not found: {proposal_id}")

        _, title, total_amount, discount_global, created_at, client_name = row

        cursor.execute(
            q(
                """
                SELECT
                    pi.qty,
                    pi.price_base,
                    pi.discount_item,
                    pi.price_final,
                    p.code,
                    p.name
                FROM proposal_items pi
                JOIN products p ON pi.sku_id = p.id
                WHERE pi.proposal_id = %s
                ORDER BY pi.id
                """
            ),
            (proposal_id,),
        )
        items_rows = cursor.fetchall()

        items: list[dict[str, Any]] = []
        for qty, price_base, discount_item, price_final, sku, item_type in items_rows:
            items.append(
                {
                    "qty": int(qty),
                    "sku": sku,
                    "type": item_type,
                    "price_base": float(price_base) if price_base is not None else 0.0,
                    "discount_item": int(discount_item) if discount_item is not None else 0,
                    # price_final here = price after item-discount (global discount applied later)
                    "price_final": float(price_final) if price_final is not None else 0.0,
                }
            )

        return {
            "id": proposal_id,
            "title": title,
            "client_name": client_name,
            "total_amount": float(total_amount) if total_amount is not None else 0.0,
            "discount_global": int(discount_global) if discount_global is not None else 0,
            "created_at": created_at,
            "items": items,
        }
    finally:
        conn.close()


def _format_ru_number(value: float) -> str:
    # Keep it consistent with existing kp_template rendering.
    return f"{value:,.0f}".replace(",", " ")


def send_proposal_email(proposal_id: int, to_email: str, subject: str) -> bool:
    """Send proposal as HTML email via SMTP (rendered via Jinja2 template)."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.yandex.ru")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        # Don't throw: keep behavior consistent with old main.py implementation.
        return False

    proposal = _get_proposal_for_email(proposal_id)

    global_discount = int(proposal.get("discount_global") or 0)
    global_multiplier = 1 - global_discount / 100.0

    items_for_template: list[dict[str, Any]] = []
    for item in proposal["items"]:
        price_final_global = float(item["price_final"]) * global_multiplier
        qty = int(item["qty"])
        items_for_template.append(
            {
                "sku": item["sku"],
                "type": item["type"],
                "qty": qty,
                "price_base": _format_ru_number(float(item["price_base"])),
                "discount_item": int(item["discount_item"]),
                "price_final_global": _format_ru_number(price_final_global),
                "row_total": _format_ru_number(price_final_global * qty),
            }
        )

    # created_at is ISO string or datetime-ish depending on DB driver;
    # old code used proposal['created_at'][:10]
    created_at = proposal.get("created_at")
    if isinstance(created_at, str):
        created_date_short = created_at[:10]
    elif isinstance(created_at, datetime):
        created_date_short = created_at.date().isoformat()
    else:
        created_date_short = ""

    ctx = {
        "proposal": proposal,
        "items": items_for_template,
        "created_date_short": created_date_short,
        "global_discount": global_discount,
        "total_amount_formatted": _format_ru_number(float(proposal.get("total_amount") or 0.0)),
    }

    template = _jinja_env.get_template("email_proposal.html")
    html_body = template.render(ctx)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True
    except Exception:
        return False
