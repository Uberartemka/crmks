from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException

from db import _use_pg, get_db, q
from db_async import execute as async_execute
from db_async import fetch_all as async_fetch_all
from db_async import fetch_one as async_fetch_one
from db_async import fetch_val as async_fetch_val

logger = logging.getLogger("HHB_B2B")

STATUS_MAP: dict[str, str] = {
    "todo": "todo",
    "open": "todo",
    "in_progress": "in_progress",
    "blocked": "blocked",
    "done": "done",
    "completed": "done",
}


def _map_task_row(r: Sequence[Any]) -> Dict[str, Any]:
    task_id = r[0]
    task_assigned_to = r[1]
    raw_status = r[9]
    task_status = STATUS_MAP.get(raw_status, raw_status)

    return {
        "id": task_id,
        "title": r[5],
        "description": r[6],
        "status": task_status,
        "priority": r[7],
        "due_date": r[8],
        "assignee_id": task_assigned_to,
        "assignee_name": r[13],
        "client_id": r[3],
        "call_id": r[4],
        "tags": [],
        "created_at": r[11] or "",
        "updated_at": r[12] or "",
    }


async def list_tasks_endpoint(
    status: Optional[str],
    client_id: Optional[int],
    current_user: Dict[str, Any],
) -> List[Dict[str, Any]]:
    logger.info(
        f"[list_tasks] Запрос от user={current_user.get('name')} "
        f"(id={current_user.get('id')}, role={current_user.get('role')}), "
        f"status={status}, client_id={client_id}"
    )

    if _use_pg:
        sql = """
            SELECT t.id, t.assigned_to, t.created_by, t.lead_id, t.call_id, t.title, t.description, 
                   t.priority, t.due_date, t.status, t.source, t.created_at, t.updated_at, u.name as assignee_name
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE 1=1
        """
        params: List[object] = []

        # Обычный сотрудник видит только свои задачи
        if current_user.get("role") == "employee":
            sql += " AND assigned_to = %s"
            params.append(current_user["id"])

        if status:
            sql += " AND status = %s"
            params.append(status)

        if client_id is not None:
            sql += " AND lead_id = %s"
            params.append(client_id)

        sql += " ORDER BY id DESC"

        rows = await async_fetch_all(q(sql), tuple(params))
        return [_map_task_row(r) for r in rows]

    # --- SQLite (sync legacy) ---
    conn = get_db()
    cursor = conn.cursor()

    sql = """
        SELECT t.id, t.assigned_to, t.created_by, t.lead_id, t.call_id, t.title, t.description, 
               t.priority, t.due_date, t.status, t.source, t.created_at, t.updated_at, u.name as assignee_name
        FROM tasks t
        LEFT JOIN users u ON u.id = t.assigned_to
        WHERE 1=1
    """
    params: List[object] = []

    if current_user.get("role") == "employee":
        sql += " AND assigned_to = %s"
        params.append(current_user["id"])

    if status:
        sql += " AND status = %s"
        params.append(status)

    if client_id is not None:
        sql += " AND lead_id = %s"
        params.append(client_id)

    sql += " ORDER BY id DESC"

    cursor.execute(q(sql), tuple(params))
    rows = cursor.fetchall()
    conn.close()

    return [_map_task_row(r) for r in rows]


async def create_task_endpoint(
    body: Dict[str, Any],
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    title = body.get("title", "Без названия")
    description = body.get("description", "")
    status = body.get("status", "todo")
    priority = body.get("priority", "normal")
    due_date = body.get("due_date", "")
    assignee_id = body.get("assignee_id") or current_user["id"]
    client_id = body.get("client_id")
    call_id = body.get("call_id")

    now = datetime.now().isoformat()

    if _use_pg:
        new_id = await async_fetch_val(
            """
            INSERT INTO tasks (assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                assignee_id,
                current_user["username"],
                client_id,
                call_id,
                title,
                description,
                priority,
                due_date,
                status,
                "manual",
                now,
                now,
            ),
        )

        assignee_name_row = await async_fetch_one(
            "SELECT name FROM users WHERE id = %s",
            (assignee_id,),
        )
        assignee_name = assignee_name_row[0] if assignee_name_row else None

        return {
            "id": new_id,
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "due_date": due_date,
            "assignee_id": assignee_id,
            "assignee_name": assignee_name,
            "client_id": client_id,
            "call_id": call_id,
            "tags": [],
            "created_at": now,
            "updated_at": now,
        }

    # --- SQLite (sync legacy) ---
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q(
            """
            INSERT INTO tasks (assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        ),
        (
            assignee_id,
            current_user["username"],
            client_id,
            call_id,
            title,
            description,
            priority,
            due_date,
            status,
            "manual",
            now,
            now,
        ),
    )

    if _use_pg:
        cursor.execute("SELECT LASTVAL()")
    else:
        cursor.execute("SELECT last_insert_rowid()")

    new_id = cursor.fetchone()[0]

    cursor.execute(q("SELECT name FROM users WHERE id = %s"), (assignee_id,))
    user_row = cursor.fetchone()
    assignee_name = user_row[0] if user_row else None

    conn.commit()
    conn.close()

    return {
        "id": new_id,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "due_date": due_date,
        "assignee_id": assignee_id,
        "assignee_name": assignee_name,
        "client_id": client_id,
        "call_id": call_id,
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }


async def update_task_endpoint(
    task_id: int,
    body: Dict[str, Any],
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    if _use_pg:
        row = await async_fetch_one(
            "SELECT id, assigned_to FROM tasks WHERE id = %s",
            (task_id,),
        )
        if not row:
            raise HTTPException(404, "Задача не найдена")

        assigned_to = row[1]
        if current_user.get("role") == "employee" and assigned_to != current_user["id"]:
            raise HTTPException(403, "Forbidden")

        fields: List[str] = []
        values: List[object] = []

        col_map = {
            "title": "title",
            "description": "description",
            "status": "status",
            "priority": "priority",
            "due_date": "due_date",
            "assignee_id": "assigned_to",
            "client_id": "lead_id",
        }

        for k, v in body.items():
            if k in col_map:
                fields.append(f"{col_map[k]} = %s")
                values.append(v)

        if fields:
            now = datetime.now().isoformat()
            fields.append("updated_at = %s")
            values.append(now)

            sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s"
            values.append(task_id)
            await async_execute(q(sql), tuple(values))

        r = await async_fetch_one(
            q(
                """
                SELECT t.id, t.assigned_to, t.created_by, t.lead_id, t.call_id, t.title, t.description, 
                       t.priority, t.due_date, t.status, t.source, t.created_at, t.updated_at, u.name
                FROM tasks t
                LEFT JOIN users u ON u.id = t.assigned_to
                WHERE t.id = %s
                """
            ),
            (task_id,),
        )
        if not r:
            raise HTTPException(404, "Задача не найдена")

        return {
            "id": r[0],
            "title": r[5],
            "description": r[6],
            "status": r[9],
            "priority": r[7],
            "due_date": r[8],
            "assignee_id": r[1],
            "assignee_name": r[13],
            "client_id": r[3],
            "call_id": r[4],
            "tags": [],
            "created_at": r[11] or "",
            "updated_at": r[12] or "",
        }

    # --- SQLite (sync legacy) ---
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT id, assigned_to FROM tasks WHERE id = %s"), (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Задача не найдена")

    assigned_to = row[1]
    if current_user.get("role") == "employee" and assigned_to != current_user["id"]:
        conn.close()
        raise HTTPException(403, "Forbidden")

    fields: List[str] = []
    values: List[object] = []

    col_map = {
        "title": "title",
        "description": "description",
        "status": "status",
        "priority": "priority",
        "due_date": "due_date",
        "assignee_id": "assigned_to",
        "client_id": "lead_id",
    }

    for k, v in body.items():
        if k in col_map:
            fields.append(f"{col_map[k]} = %s")
            values.append(v)

    if fields:
        now = datetime.now().isoformat()
        fields.append("updated_at = %s")
        values.append(now)

        sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s"
        values.append(task_id)
        cursor.execute(q(sql), tuple(values))
        conn.commit()

    cursor.execute(
        q(
            """
            SELECT t.id, t.assigned_to, t.created_by, t.lead_id, t.call_id, t.title, t.description, 
                   t.priority, t.due_date, t.status, t.source, t.created_at, t.updated_at, u.name
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE t.id = %s
            """
        ),
        (task_id,),
    )
    r = cursor.fetchone()
    conn.close()

    if not r:
        raise HTTPException(404, "Задача не найдена")

    return {
        "id": r[0],
        "title": r[5],
        "description": r[6],
        "status": r[9],
        "priority": r[7],
        "due_date": r[8],
        "assignee_id": r[1],
        "assignee_name": r[13],
        "client_id": r[3],
        "call_id": r[4],
        "tags": [],
        "created_at": r[11] or "",
        "updated_at": r[12] or "",
    }


async def delete_task_endpoint(
    task_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    if _use_pg:
        row = await async_fetch_one(
            "SELECT id, assigned_to FROM tasks WHERE id = %s",
            (task_id,),
        )
        if not row:
            raise HTTPException(404, "Задача не найдена")

        assigned_to = row[1]
        if current_user.get("role") == "employee" and assigned_to != current_user["id"]:
            raise HTTPException(403, "Forbidden")

        await async_execute(q("DELETE FROM tasks WHERE id = %s"), (task_id,))
        return {"ok": True}

    # --- SQLite (sync legacy) ---
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT id, assigned_to FROM tasks WHERE id = %s"), (task_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Задача не найдена")

    assigned_to = row[1]
    if current_user.get("role") == "employee" and assigned_to != current_user["id"]:
        conn.close()
        raise HTTPException(403, "Forbidden")

    cursor.execute(q("DELETE FROM tasks WHERE id = %s"), (task_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


async def my_tasks(
    current_user: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if _use_pg:
        rows = await async_fetch_all(
            q(
                """
                SELECT id, assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at, completed_at 
                FROM tasks 
                WHERE assigned_to = %s AND status IN ('open', 'todo')
                ORDER BY 
                    CASE priority 
                        WHEN 'urgent' THEN 4
                        WHEN 'high' THEN 3
                        WHEN 'normal' THEN 2
                        WHEN 'low' THEN 1
                        ELSE 0 
                    END DESC,
                    due_date ASC
                """
            ),
            (current_user["id"],),
        )

        return [
            {
                "id": r[0],
                "assigned_to": r[1],
                "created_by": r[2],
                "lead_id": r[3],
                "call_id": r[4],
                "title": r[5],
                "description": r[6],
                "priority": r[7],
                "due_date": r[8],
                "status": "todo" if r[9] == "open" else r[9],
                "source": r[10],
                "created_at": r[11],
                "completed_at": r[12],
            }
            for r in rows
        ]

    # --- SQLite (sync legacy) ---
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q(
            """
            SELECT id, assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at, completed_at 
            FROM tasks 
            WHERE assigned_to = %s AND status IN ('open', 'todo')
            ORDER BY 
                CASE priority 
                    WHEN 'urgent' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0 
                END DESC,
                due_date ASC
            """
        ),
        (current_user["id"],),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "assigned_to": r[1],
            "created_by": r[2],
            "lead_id": r[3],
            "call_id": r[4],
            "title": r[5],
            "description": r[6],
            "priority": r[7],
            "due_date": r[8],
            "status": "todo" if r[9] == "open" else r[9],
            "source": r[10],
            "created_at": r[11],
            "completed_at": r[12],
        }
        for r in rows
    ]


async def complete_task(
    task_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    if _use_pg:
        exists = await async_fetch_one(
            q("SELECT id FROM tasks WHERE id = %s AND assigned_to = %s"),
            (task_id, current_user["id"]),
        )
        if not exists:
            raise HTTPException(404, "Задача не найдена или принадлежит другому пользователю")

        now = datetime.now().isoformat()
        await async_execute(
            q("UPDATE tasks SET status = 'done', completed_at = %s WHERE id = %s"),
            (now, task_id),
        )
        return {"ok": True}

    # --- SQLite (sync legacy) ---
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q("SELECT id FROM tasks WHERE id = %s AND assigned_to = %s"),
        (task_id, current_user["id"]),
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(404, "Задача не найдена или принадлежит другому пользователю")

    now = datetime.now().isoformat()
    cursor.execute(
        q("UPDATE tasks SET status = 'done', completed_at = %s WHERE id = %s"),
        (now, task_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}
