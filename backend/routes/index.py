from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth_deps import get_current_user as _get_current_user
from token_store import set_token_sync, delete_token_sync
from db import get_db, q
from schemas.auth import UserCreate, UserLogin
from utils.auth_utils import hash_password, verify_password
from utils.db_utils import get_last_id
from utils.web_search import _search_email_from_db, _search_web_email
logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["index"])


def get_current_user_dep(request: Request) -> dict:
    return _get_current_user(request)


class PlanCreate(BaseModel):
    user_id: int
    month: int
    year: int
    calls_target: int
    registrations_target: int


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


@router.post("/api/auth/login")
def login(data: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("SELECT id, password_hash, name, role, client_id FROM users WHERE username = %s"),
        (data.username,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not verify_password(data.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = secrets.token_urlsafe(32)
    set_token_sync(token, row[0])
    return {
        "token": token,
        "user": {
            "id": row[0],
            "username": data.username,
            "name": row[2],
            "role": row[3],
            "client_id": row[4],
        },
    }


@router.post("/api/auth/logout")
def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        delete_token_sync(token)
    return {"detail": "Logged out"}


@router.get("/api/auth/me")
def me(current_user: dict = Depends(get_current_user_dep)):
    return current_user


@router.get("/api/users")
def list_users(current_user: dict = Depends(get_current_user_dep)):
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT id, username, name, role FROM users ORDER BY name"))
    rows = cursor.fetchall()
    conn.close()

    return [{"id": r[0], "username": r[1], "name": r[2], "role": r[3]} for r in rows]


@router.post("/api/users")
def create_user(data: UserCreate, current_user: dict = Depends(get_current_user_dep)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    try:
        cursor.execute(
            q(
                """
                INSERT INTO users (username, password_hash, name, role, created_at)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """
            ),
            (data.username, hash_password(data.password), data.name, data.role, now),
        )
        conn.commit()
        uid = get_last_id(cursor)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Username already exists or invalid data: {e}")

    conn.close()
    return {"id": uid, "username": data.username, "name": data.name, "role": data.role}


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, current_user: dict = Depends(get_current_user_dep)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM users WHERE id = %s"), (user_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": user_id}


@router.get("/api/plans")
def list_plans(current_user: dict = Depends(get_current_user_dep)):
    conn = get_db()
    cursor = conn.cursor()

    if current_user["role"] in ("admin", "manager"):
        cursor.execute(
            q(
                """
                SELECT p.id, p.user_id, u.name, p.month, p.year, p.calls_target, p.registrations_target
                FROM employee_plans p
                JOIN users u ON u.id = p.user_id
                ORDER BY p.year DESC, p.month DESC
                """
            )
        )
    else:
        cursor.execute(
            q(
                """
                SELECT p.id, p.user_id, u.name, p.month, p.year, p.calls_target, p.registrations_target
                FROM employee_plans p
                JOIN users u ON u.id = p.user_id
                WHERE p.user_id = %s
                ORDER BY p.year DESC, p.month DESC
                """
            ),
            (current_user["id"],),
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "user_id": r[1],
            "user_name": r[2],
            "month": r[3],
            "year": r[4],
            "calls_target": r[5],
            "registrations_target": r[6],
        }
        for r in rows
    ]


@router.post("/api/plans")
def create_plan(data: PlanCreate, current_user: dict = Depends(get_current_user_dep)):
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute(
        q(
            """
            INSERT INTO employee_plans (user_id, month, year, calls_target, registrations_target, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """
        ),
        (data.user_id, data.month, data.year, data.calls_target, data.registrations_target, now, now),
    )
    conn.commit()
    pid = get_last_id(cursor)
    conn.close()

    return {
        "id": pid,
        "user_id": data.user_id,
        "month": data.month,
        "year": data.year,
        "calls_target": data.calls_target,
        "registrations_target": data.registrations_target,
    }


@router.get("/api/search/email")
async def search_email(q: str):
    email, source = await asyncio.to_thread(_search_email_from_db, q)

    if not email:
        try:
            web_email = await asyncio.wait_for(asyncio.to_thread(_search_web_email, q), timeout=6.0)
            if web_email:
                email = web_email
                source = "web"
        except asyncio.TimeoutError:
            logger.warning(f"[WebSearch] Timeout for query: {q}")
        except Exception as e:
            logger.warning(f"[WebSearch] Error: {e}")

    return {"email": email, "source": source}


def register_routes(app) -> None:
    # Public/auth/search endpoints
    app.include_router(router)

    # Startup hooks (scheduler) + middleware (rate limiter)
    from startup.scheduler_startup import register_scheduler_startup
    from rate_limiter import register_rate_limiter
    register_scheduler_startup(app)
    register_rate_limiter(app)

    # AI endpoints
    from ai_routes import router as ai_chat_router
    app.include_router(ai_chat_router)

    from routes.ai_search import router as ai_search_router
    app.include_router(ai_search_router)

    from routes.ai_claude_agent import router as ai_claude_router
    app.include_router(ai_claude_router)

    from routes.agent_parser import router as agent_parser_router
    app.include_router(agent_parser_router)

    # Queue + task worker endpoints
    from routes.queue_webhooks import router as queue_webhooks_router

    app.include_router(queue_webhooks_router)

    from routes.queue_legacy import router as queue_legacy_router

    app.include_router(queue_legacy_router)

    # Tasks
    from routes.tasks import router as tasks_router

    app.include_router(tasks_router)

    # Notes
    from routes.notes import router as notes_router

    app.include_router(notes_router)

    # Defects
    from routes.defects import router as defects_router

    app.include_router(defects_router)

    # Machinery
    from routes.machinery import router as machinery_router

    app.include_router(machinery_router)

    from routes.tasks_legacy import router as tasks_legacy_router

    app.include_router(tasks_legacy_router)

    # Daily plan (генерация планов для команды/пользователя)
    from routes.daily_plan import router as daily_plan_router

    app.include_router(daily_plan_router)

    # Agent endpoints
    from routes.agent import router as agent_router

    app.include_router(agent_router)

    # Catalog + clients + KPI plans
    from routes.catalog_skus import router as catalog_skus_router

    app.include_router(catalog_skus_router)

    from routes.catalog_v1 import router as catalog_v1_router
    app.include_router(catalog_v1_router)

    from routes.clients import router as clients_router

    app.include_router(clients_router)

    from routes.kpi_plans import router as kpi_plans_router

    app.include_router(kpi_plans_router)

    # Calendar / events
    from routes.calendar import router as calendar_router

    app.include_router(calendar_router)

    # Proposals / KP
    from routes.proposals import router as proposals_router

    app.include_router(proposals_router)

    # Leads
    from routes.leads import router as leads_router

    app.include_router(leads_router)

    # Calls
    from routes.calls import router as calls_router

    app.include_router(calls_router)
