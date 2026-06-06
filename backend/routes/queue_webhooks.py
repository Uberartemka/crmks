from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_db, q, _use_pg
from services.queue_service import init_queue_manager as _init_queue_manager
from services.queue_service import get_queue_manager as _get_queue_manager

from auth import verify_b2b_token

logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["queue", "webhooks"])


# Instantiate queue manager and start worker thread on server boot
_init_queue_manager()
get_queue_manager = _get_queue_manager


class TaskInput(BaseModel):
    task_type: str
    payload: Dict[str, Any]
    max_retries: int = 3


@router.get("/")
def read_root():
    return {
        "status": "online",
        "service": "HHB B2B Integration Queue",
        "endpoints": {
            "swagger": "/docs",
            "add_task": "POST /api/queue/add",
            "list_tasks": "GET /api/queue/list",
            "stats": "GET /api/queue/stats",
        },
    }


@router.post("/api/queue/add")
def add_task(input_data: TaskInput):
    valid_types = ["1c_sync", "crm_lead", "email_invoice"]
    if input_data.task_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Невалидный тип задачи. Допустимые: {valid_types}",
        )

    manager = get_queue_manager()
    task_id = manager.add_task(input_data.task_type, input_data.payload, input_data.max_retries)
    return {
        "status": "added",
        "task_id": task_id,
        "detail": "Задача успешно добавлена в очередь на обработку.",
    }


@router.get("/api/queue/status/{task_id}")
def get_task_status(task_id: int):
    manager = get_queue_manager()
    status = manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Задача с таким ID не найдена в базе данных.")
    return status


@router.get("/api/queue/list", dependencies=[Depends(verify_b2b_token)])
def list_tasks():
    manager = get_queue_manager()
    return manager.list_tasks(limit=50)


@router.get("/api/queue/stats", dependencies=[Depends(verify_b2b_token)])
def get_stats():
    manager = get_queue_manager()
    return manager.get_queue_stats()


@router.post("/api/queue/retry/{task_id}", dependencies=[Depends(verify_b2b_token)])
def retry_task(task_id: int):
    manager = get_queue_manager()
    status = manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    if status["status"] != "failed":
        raise HTTPException(
            status_code=400,
            detail="Перезапустить можно только задачи со статусом 'failed'.",
        )

    manager.retry_task(task_id)
    return {
        "status": "queued",
        "task_id": task_id,
        "detail": "Задача возвращена в статус 'pending' на повторную обработку.",
    }


# === WEBHOOK ENDPOINTS (PUSH INTEGRATIONS) ===

class BitrixWebhookInput(BaseModel):
    event: str
    data: Dict[str, Any]


class OneCWebhookInput(BaseModel):
    sku: str
    new_stock: int
    new_price: float


class BitrixTelephonyInput(BaseModel):
    event: str  # e.g. ONVOXIMPLANTCALLSTART, ONVOXIMPLANTCALLEND
    data: Dict[str, Any]


@router.post("/api/webhooks/bitrix", dependencies=[Depends(verify_b2b_token)])
def bitrix_webhook(payload: BitrixWebhookInput):
    logger.info(f"[Webhook] Получено событие от Битрикс24: {payload.event}")

    deal_id = payload.data.get("FIELDS", {}).get("ID") or payload.data.get("ID")
    task_payload = {
        "event_type": payload.event,
        "deal_id": deal_id,
        "raw_data": payload.data,
    }

    manager = get_queue_manager()
    task_id = manager.add_task("crm_lead", task_payload, max_retries=3)
    return {
        "status": "received",
        "event_processed": payload.event,
        "task_id": task_id,
        "detail": "Событие Битрикс24 зарегистрировано и добавлено в асинхронную очередь воркера.",
    }


@router.post("/api/webhooks/bitrix/telephony", dependencies=[Depends(verify_b2b_token)])
def bitrix_telephony_webhook(payload: BitrixTelephonyInput):
    """Receive Bitrix24 telephony events and auto-log calls."""
    logger.info(f"[Webhook] Bitrix telephony: {payload.event} data={payload.data}")

    call_data = payload.data.get("data", {}) or payload.data
    call_id = call_data.get("CALL_ID") or call_data.get("CALL_ID") or call_data.get("ID")
    phone_number = call_data.get("PHONE_NUMBER") or call_data.get("CALLER_ID")
    user_id = call_data.get("PORTAL_USER_ID") or call_data.get("USER_ID")
    duration = call_data.get("CALL_DURATION") or 0
    status = call_data.get("CALL_STATUS") or call_data.get("CALL_FAILED_REASON") or "unknown"
    record_url = call_data.get("CALL_RECORD_URL") or call_data.get("RECORD_URL")
    direction = call_data.get("CALL_DIRECTION") or "outgoing"
    crm_entity_type = call_data.get("CRM_ENTITY_TYPE")  # LEAD, CONTACT, COMPANY
    crm_entity_id = call_data.get("CRM_ENTITY_ID")

    event_upper = (payload.event or "").upper()
    is_start = "CALLSTART" in event_upper
    is_end = "CALLEND" in event_upper

    status_map = {
        "success": "completed",
        "failed": "no_answer",
        "declined": "rejected",
        "missed": "no_answer",
        "busy": "no_answer",
        "not_available": "no_answer",
        " congestion": "no_answer",
    }

    mapped_status = str(status).lower()
    if is_start:
        mapped_status = "in_progress"
        duration = 0
        record_url = None
    elif is_end:
        mapped_status = status_map.get(str(status).lower(), str(status).lower())

    lead_id = None
    client_name = "Unknown"
    conn = get_db()
    cursor = conn.cursor()
    try:
        if crm_entity_type == "LEAD" and crm_entity_id:
            cursor.execute(q("SELECT id, name FROM parsed_leads WHERE id = %s"), (crm_entity_id,))
        elif phone_number:
            digits = "".join(c for c in str(phone_number) if c.isdigit())
            if _use_pg:
                cursor.execute(
                    "SELECT id, name FROM parsed_leads WHERE REGEXP_REPLACE(contacts, '[^0-9]', '', 'g') LIKE %s LIMIT 1",
                    ("%" + digits + "%",),
                )
            else:
                cursor.execute(
                    "SELECT id, name FROM parsed_leads WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(contacts, '+', ''), '-', ''), '(', ''), ')', ''), ' ', '') LIKE ? LIMIT 1",
                    ("%" + digits + "%",),
                )

        row = cursor.fetchone()
        if row:
            lead_id = row[0]
            client_name = row[1]
    except Exception as e:
        logger.warning(f"[BitrixTelephony] Lead lookup failed: {e}")

    try:
        cursor.execute(q("SELECT id FROM call_logs WHERE bitrix_call_id = %s"), (str(call_id),))
        existing = cursor.fetchone()
        now = datetime.now().isoformat()

        if is_start:
            if existing:
                cursor.execute(
                    q("""
                        UPDATE call_logs
                        SET status = %s, to_number = %s, direction = %s, updated_at = %s
                        WHERE bitrix_call_id = %s
                    """),
                    (
                        mapped_status,
                        str(phone_number),
                        str(direction).lower(),
                        now,
                        str(call_id),
                    ),
                )
            else:
                cursor.execute(
                    q("""
                        INSERT INTO call_logs (user_id, lead_id, client_name, to_number, direction,
                            call_date, status, duration, recording_url, bitrix_call_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """),
                    (
                        user_id,
                        lead_id,
                        client_name,
                        str(phone_number),
                        str(direction).lower(),
                        now[:10],
                        mapped_status,
                        0,
                        None,
                        str(call_id),
                        now,
                        now,
                    ),
                )

        else:
            # END (or any other non-start event): full update with duration/recording
            if existing:
                cursor.execute(
                    q("""
                        UPDATE call_logs
                        SET status = %s, duration = %s, recording_url = %s,
                            to_number = %s, direction = %s, updated_at = %s
                        WHERE bitrix_call_id = %s
                    """),
                    (
                        mapped_status,
                        int(duration) if duration else 0,
                        record_url,
                        str(phone_number),
                        str(direction).lower(),
                        now,
                        str(call_id),
                    ),
                )
            else:
                cursor.execute(
                    q("""
                        INSERT INTO call_logs (user_id, lead_id, client_name, to_number, direction,
                            call_date, status, duration, recording_url, bitrix_call_id, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """),
                    (
                        user_id,
                        lead_id,
                        client_name,
                        str(phone_number),
                        str(direction).lower(),
                        now[:10],
                        mapped_status,
                        int(duration) if duration else 0,
                        record_url,
                        str(call_id),
                        now,
                        now,
                    ),
                )

        conn.commit()
        logger.info(
            f"[BitrixTelephony] Call {call_id} logged/updated: event={payload.event} status={mapped_status} duration={duration}"
        )
    except Exception as e:
        logger.error(f"[!] [BitrixTelephony] Error saving call log: {e}")
        logger.error(traceback.format_exc())
    finally:
        conn.close()

    return {"status": "received", "event": payload.event, "call_id": call_id}


@router.post("/api/webhooks/1c", dependencies=[Depends(verify_b2b_token)])
def one_c_webhook(payload: OneCWebhookInput):
    logger.info(f"[Webhook] Получено обновление остатков из 1С для артикула: {payload.sku}")

    task_payload = {
        "sku": payload.sku,
        "new_stock": payload.new_stock,
        "new_price": payload.new_price,
    }

    manager = get_queue_manager()
    task_id = manager.add_task("1c_sync", task_payload, max_retries=3)
    return {
        "status": "received",
        "sku_updated": payload.sku,
        "task_id": task_id,
        "detail": "Завиршение ...",  # kept compatible but can be adjusted
    }
