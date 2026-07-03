from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader

from auth_deps import get_current_user
from db import get_db, q
from schemas.proposals import (
    DiscountInput,
    ProposalInput,
    ProposalItemInput,
    SendEmailInput,
)
from services.email_service import send_proposal_email as send_proposal_email_service
from services.proposal_service import recalc_proposal_total
from services.queue_service import get_queue_manager
from utils.db_utils import get_last_id

logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["proposals"])

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))


def _get_optional_qm() -> Any | None:
    try:
        return get_queue_manager()
    except HTTPException:
        return None


@router.post("/api/proposals")
def create_proposal(
    data: ProposalInput, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("""
        INSERT INTO proposals (client_id, created_by, title, total_amount, discount_global, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """),
        (data.client_id, current_user["id"], data.title or f"КП от {now[:10]}", 0, data.discount_global, "draft", now, now),
    )
    proposal_id = get_last_id(cursor)
    cursor.execute("SELECT COUNT(*) FROM proposals")
    seq_num = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    logger.info(
        f"[Proposal] Создано КП #{proposal_id} (seq: {seq_num}) для клиента {data.client_id} user={current_user['id']}"
    )
    return {"status": "created", "proposal_id": proposal_id, "seq_num": seq_num}


@router.get("/api/proposals")
def list_proposals() -> list[dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.id, p.client_id, c.name as client_name, p.title, p.total_amount,
               p.discount_global, p.status, p.email_sent, p.created_at,
               ROW_NUMBER() OVER (ORDER BY p.id) as seq_num
        FROM proposals p LEFT JOIN clients c ON p.client_id = c.id
        ORDER BY p.id DESC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "client_id": r[1],
            "client_name": r[2],
            "title": r[3],
            "total_amount": float(r[4]) if r[4] else 0,
            "discount_global": r[5],
            "status": r[6],
            "email_sent": r[7],
            "created_at": r[8],
            "seq_num": r[9],
        }
        for r in rows
    ]


@router.get("/api/proposals/{proposal_id}")
def get_proposal(proposal_id: int) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("""
        SELECT sub.id, sub.client_id, sub.client_name, sub.email, sub.title, sub.total_amount, sub.discount_global,
               sub.status, sub.email_sent, sub.created_at, sub.seq_num
        FROM (
            SELECT p.id, p.client_id, c.name as client_name, c.email, p.title, p.total_amount, p.discount_global,
                   p.status, p.email_sent, p.created_at,
                   ROW_NUMBER() OVER (ORDER BY p.id) as seq_num
            FROM proposals p LEFT JOIN clients c ON p.client_id = c.id
        ) sub
        WHERE sub.id = %s
        """),
        (proposal_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="КП не найдено.")

    proposal = {
        "id": row[0],
        "client_id": row[1],
        "client_name": row[2],
        "client_email": row[3],
        "title": row[4],
        "total_amount": float(row[5]) if row[5] else 0,
        "discount_global": row[6],
        "status": row[7],
        "email_sent": row[8],
        "created_at": row[9],
        "seq_num": row[10],
    }

    cursor.execute(
        q("""
        SELECT pi.id, pi.sku_id, p.code, p.name, b.name, pi.qty, pi.price_base, pi.discount_item, pi.price_final
        FROM proposal_items pi
                JOIN products p ON pi.sku_id = p.id
                LEFT JOIN brands b ON b.id = p.brand_id
        WHERE pi.proposal_id = %s
        """),
        (proposal_id,),
    )

    items: list[dict[str, Any]] = []
    for r in cursor.fetchall():
        items.append(
            {
                "id": r[0],
                "sku_id": r[1],
                "sku": r[2],
                "type": r[3],
                "brand": r[4],
                "qty": r[5],
                "price_base": float(r[6]) if r[6] else 0,
                "discount_item": r[7],
                "price_final": float(r[8]) if r[8] else 0,
            }
        )

    proposal["items"] = items
    conn.close()
    return proposal


@router.get("/kp/{proposal_id}", response_class=HTMLResponse)
def render_proposal_public(proposal_id: int) -> str:
    """Public proposal page — no auth required."""
    proposal = get_proposal(proposal_id)

    conn = get_db()
    cursor = conn.cursor()

    # Get manager info
    manager = {"name": "", "phone": "", "email": "", "initials": "—"}

    cursor.execute(q("SELECT created_by FROM proposals WHERE id = %s"), (proposal_id,))
    row = cursor.fetchone()
    created_by = row[0] if row else None

    if created_by:
        cursor.execute(q("SELECT name, username FROM users WHERE id = %s"), (created_by,))
        urow = cursor.fetchone()
        if urow:
            manager["name"] = urow[0]
            manager["initials"] = "".join([p[0].upper() for p in urow[0].split()[:2] if p])

    conn.close()

    # Build template context
    today = datetime.now()
    valid = today + timedelta(days=14)

    global_discount = int(proposal.get("discount_global") or 0)
    global_multiplier = 1 - global_discount / 100

    total_before = sum(item["price_base"] * item["qty"] for item in proposal["items"])
    total_after_item = sum(item["price_final"] * item["qty"] for item in proposal["items"])
    total_after = total_after_item * global_multiplier
    discount_amount = total_before - total_after
    vat = total_after * 0.2

    raw_title = proposal.get("title", "Коммерческое предложение")
    formatted_title = raw_title
    if isinstance(raw_title, str) and raw_title.startswith("КП от "):
        date_part = raw_title.replace("КП от ", "", 1)
        try:
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            formatted_title = f"КП от {dt.strftime('%d.%m.%Y')}"
        except Exception:
            formatted_title = raw_title

    ctx = {
        "kp_id": proposal_id,
        "kp_number": f"#{proposal.get('seq_num', proposal_id)}",
        "date": today.strftime("%d.%m.%Y"),
        "valid_until": valid.strftime("%d.%m.%Y"),
        "title": formatted_title,
        "client_company": proposal.get("client_name") or "Клиент",
        "client_address": "",
        "client_phone": "",
        "client_email": proposal.get("client_email") or "",
        "items": [
            {
                "name": it.get("type") or it.get("sku"),
                "sku": it.get("sku"),
                "brand": it.get("brand") or "HHB",
                "qty": it.get("qty", 1),
                "price_base": f"{it['price_base']:,.0f}".replace(",", " "),
                "discount_item": it.get("discount_item", 0),
                # price_final in proposal_items is only "item discount".
                # Apply global discount for rendering totals.
                "price_final": it["price_final"] * global_multiplier,
            }
            for it in proposal["items"]
        ],
        "total_before_discount": f"{total_before:,.0f}".replace(",", " "),
        "discount_amount": f"{discount_amount:,.0f}".replace(",", " "),
        "vat_amount": f"{vat:,.0f}".replace(",", " "),
        "total_final": f"{total_after + vat:,.0f}".replace(",", " "),
        "delivery_days": "3–5",
        "payment_terms": "Предоплата 30% / постоплата",
        "delivery_method": "ТК «Деловые Линии» / СДЭК",
        "notes": "Цены действительны при 100% оплате в течение 3 рабочих дней. Наличие уточняйте у менеджера.",
        "manager_name": manager["name"] or "Менеджер ООО «Компонент Сервис»",
        "manager_initials": manager["initials"] or "КС",
        "manager_phone": manager.get("phone") or "+7 (473) 200-11-11",
        "manager_email": manager.get("email") or "sales@component-service.ru",
    }

    template = jinja_env.get_template("kp_template.html")
    html = template.render(ctx)
    return html


@router.post("/api/proposals/{proposal_id}/pdf/generate")
async def request_pdf_generation(
    proposal_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Асинхронная генерация PDF через очередь.
    Возвращает job_id, клиент сам опрашивает status и скачивает готовый файл.
    """
    from services.pdf_service import set_pdf_job_id

    qm = get_queue_manager()
    base_url = str(request.base_url).rstrip("/")

    job_id = qm.add_task(
        "generate_pdf",
        {"proposal_id": proposal_id, "base_url": base_url},
        max_retries=2,
    )

    # job_id => proposal_id mapping для статуса/скачивания
    set_pdf_job_id(proposal_id=proposal_id, job_id=job_id)

    return {"job_id": job_id, "status": "queued"}


@router.get("/api/proposals/{proposal_id}/pdf/status")
async def get_pdf_status(proposal_id: int) -> dict[str, Any]:
    """
    Статус PDF генерации:
    - pending: задача не готова
    - ready: можно скачивать
    - failed: ошибка (если исчерпаны попытки)
    """
    from services.pdf_service import get_pdf_job_id, get_pdf_result_path

    path = get_pdf_result_path(proposal_id)
    if path:
        return {"status": "ready", "download_url": f"/api/proposals/{proposal_id}/pdf/download"}

    job_id = get_pdf_job_id(proposal_id)
    if not job_id:
        return {"status": "pending"}

    qm = _get_optional_qm()
    if qm is None:
        return {"status": "pending"}

    job_status = qm.get_task_status(job_id)
    if not job_status:
        return {"status": "pending"}

    status = job_status.get("status")
    if status == "failed":
        return {"status": "failed", "error": job_status.get("error_message")}

    if status == "completed":
        # completed, но файл/путь еще не записан: считаем pending
        return {"status": "pending"}

    return {"status": status or "pending"}


@router.get("/api/proposals/{proposal_id}/pdf/download")
async def download_pdf(proposal_id: int) -> FileResponse:
    from services.pdf_service import get_pdf_result_path

    path = get_pdf_result_path(proposal_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF не готов")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"KP_HHB_{proposal_id}.pdf",
        background=None,
    )


# Backward compatibility: старый sync endpoint больше не генерирует PDF.
@router.get("/api/proposals/{proposal_id}/pdf")
async def download_proposal_pdf_deprecated(proposal_id: int) -> dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail="Use POST /api/proposals/{id}/pdf/generate then poll GET /api/proposals/{id}/pdf/status and GET /api/proposals/{id}/pdf/download",
    )


@router.post("/api/proposals/{proposal_id}/items")
def add_proposal_item(proposal_id: int, data: ProposalItemInput) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT price_new FROM products WHERE id = %s"), (data.sku_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="SKU не найден.")

    price_base = float(row[0])
    price_final = price_base * (1 - data.discount_item / 100)

    cursor.execute(
        q("""
        INSERT INTO proposal_items (proposal_id, sku_id, qty, price_base, discount_item, price_final)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """),
        (proposal_id, data.sku_id, data.qty, price_base, data.discount_item, price_final),
    )

    item_id = get_last_id(cursor)
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    logger.info(f"[Proposal] В КП #{proposal_id} добавлена позиция #{item_id} (SKU {data.sku_id})")
    return {"status": "added", "item_id": item_id}


@router.put("/api/proposals/{proposal_id}/items/{item_id}")
def update_proposal_item(proposal_id: int, item_id: int, data: ProposalItemInput) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("SELECT price_base FROM proposal_items WHERE id = %s AND proposal_id = %s"),
        (item_id, proposal_id),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Позиция не найдена.")

    price_base = float(row[0])
    price_final = price_base * (1 - data.discount_item / 100)

    cursor.execute(
        q("""
        UPDATE proposal_items SET qty = %s, discount_item = %s, price_final = %s WHERE id = %s
        """),
        (data.qty, data.discount_item, price_final, item_id),
    )

    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    return {"status": "updated", "item_id": item_id}


@router.delete("/api/proposals/{proposal_id}/items/{item_id}")
def delete_proposal_item(proposal_id: int, item_id: int) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("DELETE FROM proposal_items WHERE id = %s AND proposal_id = %s"),
        (item_id, proposal_id),
    )
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    logger.info(f"[Proposal] Из КП #{proposal_id} удалена позиция #{item_id}")
    return {"status": "deleted", "item_id": item_id}


@router.delete("/api/proposals/{proposal_id}")
def delete_proposal(proposal_id: int) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM proposal_items WHERE proposal_id = %s"), (proposal_id,))
    cursor.execute(q("DELETE FROM proposals WHERE id = %s"), (proposal_id,))
    conn.commit()
    conn.close()
    logger.info(f"[Proposal] Удалено КП #{proposal_id}")
    return {"status": "deleted", "proposal_id": proposal_id}


@router.delete("/api/proposals")
def delete_all_proposals() -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM proposal_items"))
    cursor.execute(q("DELETE FROM proposals"))
    conn.commit()
    conn.close()
    logger.info("[Proposal] Удалены все КП")
    return {"status": "deleted_all"}


@router.post("/api/proposals/{proposal_id}/discount")
def set_proposal_discount(proposal_id: int, data: DiscountInput) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("UPDATE proposals SET discount_global = %s, updated_at = %s WHERE id = %s"),
        (data.discount_global, datetime.now().isoformat(), proposal_id),
    )
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    logger.info(f"[Proposal] Установлена глобальная скидка {data.discount_global}% для КП #{proposal_id}")
    return {"status": "updated", "discount_global": data.discount_global}


@router.post("/api/kp/{proposal_id}/accept")
def accept_proposal(proposal_id: int) -> dict[str, Any]:
    """Client accepts the proposal via public page button."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        q("UPDATE proposals SET status = %s, accepted_at = %s, updated_at = %s WHERE id = %s"),
        ("accepted", now, now, proposal_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"[Proposal] КП #{proposal_id} принято клиентом.")
    return {"status": "accepted", "proposal_id": proposal_id}


@router.post("/api/proposals/{proposal_id}/send")
def send_proposal(proposal_id: int, data: SendEmailInput) -> dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("SELECT c.email, c.name FROM proposals p JOIN clients c ON p.client_id = c.id WHERE p.id = %s"),
        (proposal_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="КП или клиент не найден.")

    client_email = data.recipient_email or row[0]
    client_name = row[1]

    if not client_email:
        raise HTTPException(status_code=400, detail="У клиента не указан email. Введите вручную.")

    sent = send_proposal_email_service(proposal_id, client_email, data.subject)
    if not sent:
        raise HTTPException(status_code=500, detail="Не удалось отправить email. Проверьте настройки SMTP.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("UPDATE proposals SET email_sent = TRUE, status = 'sent', updated_at = %s WHERE id = %s"),
        (datetime.now().isoformat(), proposal_id),
    )
    conn.commit()
    conn.close()

    qm = _get_optional_qm()
    if qm is not None:
        qm.add_task(
            "crm_lead",
            {"type": "proposal_sent", "proposal_id": proposal_id, "client_email": client_email, "client_name": client_name},
            max_retries=3,
        )
    else:
        logger.warning(f"[Queue] CRM-задача для КП #{proposal_id} не добавлена: очередь отключена.")

    return {"status": "sent", "proposal_id": proposal_id, "recipient": client_email}


# =========================
# Deprecated wrappers
# =========================

# Legacy: /api/_deprecated/proposals/{proposal_id}/items
@router.post("/api/_deprecated/proposals/{proposal_id}/items")
def add_proposal_item_deprecated(proposal_id: int, data: ProposalItemInput) -> dict[str, Any]:
    return add_proposal_item(proposal_id=proposal_id, data=data)


@router.put("/api/_deprecated/proposals/{proposal_id}/items/{item_id}")
def update_proposal_item_deprecated(
    proposal_id: int, item_id: int, data: ProposalItemInput
) -> dict[str, Any]:
    return update_proposal_item(proposal_id=proposal_id, item_id=item_id, data=data)


@router.delete("/api/_deprecated/proposals/{proposal_id}/items/{item_id}")
def delete_proposal_item_deprecated(
    proposal_id: int, item_id: int
) -> dict[str, Any]:
    return delete_proposal_item(proposal_id=proposal_id, item_id=item_id)


@router.delete("/api/_deprecated/proposals/{proposal_id}")
def delete_proposal_deprecated(proposal_id: int) -> dict[str, Any]:
    return delete_proposal(proposal_id=proposal_id)


@router.delete("/api/_deprecated/proposals")
def delete_all_proposals_deprecated() -> dict[str, Any]:
    return delete_all_proposals()


@router.post("/api/_deprecated/proposals/{proposal_id}/discount")
def set_proposal_discount_deprecated(
    proposal_id: int, data: DiscountInput
) -> dict[str, Any]:
    return set_proposal_discount(proposal_id=proposal_id, data=data)


@router.post("/api/_deprecated/kp/{proposal_id}/accept")
def accept_proposal_deprecated(proposal_id: int) -> dict[str, Any]:
    return accept_proposal(proposal_id=proposal_id)


@router.post("/api/_deprecated/proposals/{proposal_id}/send")
def send_proposal_deprecated(
    proposal_id: int, data: SendEmailInput
) -> dict[str, Any]:
    return send_proposal(proposal_id=proposal_id, data=data)
