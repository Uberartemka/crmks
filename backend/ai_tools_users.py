"""
Tools для работы с пользователями (сотрудниками) HHB.
Клиентов здесь нет — у клиентов нет учёток (приходят из Битрикса).
"""
from db import db_cursor  # контекстник из main.py
from ai_registry import tool


@tool(
    name="find_user",
    description=(
        "Найти сотрудника HHB по имени, фамилии или username. "
        "Используй когда пользователь упоминает кого-то по имени "
        "('дай Ивану задачу', 'сколько лидов у Петрова'). "
        "Возвращает список сотрудников с id, name, username, role. "
        "Если найдено несколько — переспроси у пользователя кого именно."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Имя, фамилия, или часть username сотрудника"
            },
            "role": {
                "type": "string",
                "enum": ["admin", "manager", "employee"],
                "description": "Опционально: фильтр по роли"
            }
        },
        "required": ["query"]
    },
    roles=["admin", "manager", "employee"],
)
def find_user(ctx, query: str, role: str | None = None) -> dict:
    sql = """
        SELECT id, username, name, role
        FROM users
        WHERE (name ILIKE %s OR username ILIKE %s)
    """
    params = [f"%{query}%", f"%{query}%"]
    if role:
        sql += " AND role = %s"
        params.append(role)
    sql += " ORDER BY name LIMIT 20"

    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return {
        "count": len(rows),
        "users": [
            {"id": r[0], "username": r[1], "name": r[2], "role": r[3]}
            for r in rows
        ]
    }


@tool(
    name="list_users",
    description=(
        "Получить список всех сотрудников HHB. "
        "Используй для отчётов 'покажи всю команду' или когда нужно увидеть "
        "всех сотрудников определённой роли."
    ),
    parameters={
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": ["admin", "manager", "employee"],
                "description": "Опционально: фильтр по роли"
            }
        }
    },
    roles=["admin", "manager", "employee"],
)
def list_users(ctx, role: str | None = None) -> dict:
    sql = "SELECT id, username, name, role FROM users"
    params = []
    if role:
        sql += " WHERE role = %s"
        params.append(role)
    sql += " ORDER BY role, name"

    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return {
        "count": len(rows),
        "users": [
            {"id": r[0], "username": r[1], "name": r[2], "role": r[3]}
            for r in rows
        ]
    }
