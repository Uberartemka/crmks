"""
Tools для работы с лидами (parsed_leads).
Канбан-доска в UI рисуется из этих же данных.
"""
from db import db_cursor
from ai_registry import tool

ALLOWED_STATUSES = {"новый", "горячий", "назначен", "в_работе", "закрыт", "отказ"}


@tool(
    name="list_leads",
    description=(
        "Получить список лидов с фильтрами. "
        "Используй ВСЕГДА перед assign_leads_bulk чтобы получить реальные ID. "
        "Можно фильтровать по: статусу, назначенному менеджеру (assigned_to), "
        "категории, городу. assigned_to=null означает 'свободные, никому не назначены'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status_in": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["новый", "горячий", "назначен", "в_работе", "закрыт", "отказ"]
                },
                "description": "Список статусов для фильтра (OR)"
            },
            "assigned_to": {
                "type": ["integer", "null"],
                "description": "ID менеджера. null = только свободные лиды без назначения"
            },
            "category_contains": {
                "type": "string",
                "description": "Подстрока для поиска по категории (например 'Элеватор')"
            },
            "city_contains": {
                "type": "string",
                "description": "Подстрока для поиска по городу"
            },
            "limit": {
                "type": "integer",
                "description": "Макс. количество результатов (по умолчанию 20, макс 100)"
            }
        }
    },
    roles=["admin", "manager", "employee"],
)
def list_leads(
    ctx,
    status_in: list[str] | None = None,
    assigned_to=None,  # int | None | "null" — Kimi может прислать строку
    category_contains: str | None = None,
    city_contains: str | None = None,
    limit: int = 20,
) -> dict:
    # Нормализация: Kimi иногда шлёт "null" строкой вместо None
    if assigned_to == "null" or assigned_to == "":
        assigned_to = None
    explicit_unassigned = assigned_to is None and (
        # отличаем "не передано вообще" от "передано null"
        # → если хоть один фильтр задан, считаем что None = unassigned
        status_in or category_contains or city_contains
    )

    limit = min(max(int(limit or 20), 1), 100)

    conditions = []
    params = []

    if status_in:
        # фильтруем мусор
        clean = [s for s in status_in if s in ALLOWED_STATUSES]
        if clean:
            conditions.append(
                "status IN (" + ",".join(["%s"] * len(clean)) + ")"
            )
            params.extend(clean)

    if assigned_to is not None and assigned_to != "null":
        conditions.append("assigned_to = %s")
        params.append(int(assigned_to))
    elif explicit_unassigned:
        conditions.append("assigned_to IS NULL")

    if category_contains:
        conditions.append("category ILIKE %s")
        params.append(f"%{category_contains}%")

    if city_contains:
        conditions.append("city ILIKE %s")
        params.append(f"%{city_contains}%")

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT id, name, category, city, status, assigned_to
        FROM parsed_leads
        {where}
        ORDER BY id DESC
        LIMIT %s
    """
    params.append(limit)

    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return {
        "count": len(rows),
        "leads": [
            {
                "id": r[0],
                "name": r[1],
                "category": r[2],
                "city": r[3],
                "status": r[4],
                "assigned_to": r[5],
            }
            for r in rows
        ]
    }


@tool(
    name="assign_leads_bulk",
    description=(
        "Массово назначить лиды менеджеру. Меняет status на 'назначен' "
        "и проставляет assigned_to. "
        "ВАЖНО: перед вызовом получи реальные ID через list_leads. "
        "Доступно только admin и manager."
    ),
    parameters={
        "type": "object",
        "properties": {
            "lead_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Список ID лидов из parsed_leads",
                "minItems": 1,
                "maxItems": 50,
            },
            "manager_id": {
                "type": "integer",
                "description": "ID сотрудника-получателя (из users)"
            }
        },
        "required": ["lead_ids", "manager_id"]
    },
    roles=["admin", "manager"],
)
def assign_leads_bulk(ctx, lead_ids: list[int], manager_id: int) -> dict:
    if not lead_ids:
        return {"error": "lead_ids пуст"}
    if len(lead_ids) > 50:
        return {"error": "Слишком много лидов за раз (макс 50)"}

    with db_cursor() as cur:
        # Проверим что менеджер существует
        cur.execute("SELECT id, name, role FROM users WHERE id = %s", (manager_id,))
        user_row = cur.fetchone()
        if not user_row:
            return {"error": f"Пользователь id={manager_id} не найден"}

        # Обновляем лиды
        placeholders = ",".join(["%s"] * len(lead_ids))
        cur.execute(
            f"""
            UPDATE parsed_leads
            SET assigned_to = %s, status = 'назначен'
            WHERE id IN ({placeholders})
            RETURNING id, name, category, city
            """,
            [manager_id, *lead_ids]
        )
        updated = cur.fetchall()

    return {
        "assigned_count": len(updated),
        "manager": {"id": user_row[0], "name": user_row[1], "role": user_row[2]},
        "leads": [
            {"id": r[0], "name": r[1], "category": r[2], "city": r[3]}
            for r in updated
        ],
        "message": f"Назначено {len(updated)} лидов сотруднику {user_row[1]}",
    }
