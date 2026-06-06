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


@tool(
    name="list_tasks",
    description=(
        "Получить список открытых задач. Менеджер видит только свои задачи. "
        "Руководитель (role='manager' или 'admin') может смотреть задачи конкретного сотрудника по assigned_to."
    ),
    parameters={
        "type": "object",
        "properties": {
            "assigned_to": {
                "type": "integer",
                "description": "Опционально: ID пользователя для фильтрации"
            },
            "status": {
                "type": "string",
                "enum": ["todo", "in_progress", "done", "blocked"],
                "default": "todo",
                "description": "Статус задач"
            }
        }
    },
    roles=["admin", "manager", "employee"],
)
def list_tasks(ctx, assigned_to: int | None = None, status: str = "todo") -> dict:
    from db import q
    current_user = ctx["current_user"]
    
    # Права доступа
    target_user_id = current_user["id"]
    if current_user["role"] in ("admin", "manager") and assigned_to is not None:
        target_user_id = assigned_to
        
    sql = """
        SELECT id, assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at
        FROM tasks
        WHERE assigned_to = %s AND status = %s
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
    
    with db_cursor() as cur:
        cur.execute(q(sql), (target_user_id, status))
        rows = cur.fetchall()
        
    return {
        "count": len(rows),
        "tasks": [
            {
                "id": r[0], "assigned_to": r[1], "created_by": r[2], "lead_id": r[3], "call_id": r[4],
                "title": r[5], "description": r[6], "priority": r[7], "due_date": r[8], "status": r[9],
                "source": r[10], "created_at": r[11]
            }
            for r in rows
        ]
    }


@tool(
    name="create_task",
    description=(
        "Создать новую задачу для сотрудника (или для себя)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "assigned_to": {
                "type": "integer",
                "description": "ID сотрудника, которому назначается задача"
            },
            "title": {
                "type": "string",
                "description": "Короткий заголовок задачи (например, 'Перезвонить клиенту')"
            },
            "description": {
                "type": "string",
                "description": "Описание задачи"
            },
            "priority": {
                "type": "string",
                "enum": ["low", "normal", "high", "urgent"],
                "default": "normal"
            },
            "due_hours": {
                "type": "integer",
                "default": 24,
                "description": "Срок выполнения в часах (с текущего момента)"
            },
            "lead_id": {
                "type": "integer",
                "description": "Опционально: ID лида"
            }
        },
        "required": ["assigned_to", "title"]
    },
    roles=["admin", "manager", "employee"],
)
def create_task(ctx, assigned_to: int, title: str, description: str | None = None, priority: str = "normal", due_hours: int = 24, lead_id: int | None = None) -> dict:
    from db import q
    from datetime import datetime, timedelta
    import logging
    
    logger = logging.getLogger("HHB_B2B")
    due = (datetime.now() + timedelta(hours=due_hours)).isoformat()
    now = datetime.now().isoformat()
    
    # Security: employee может создавать задачи только для себя
    current_user = ctx["current_user"]
    if current_user["role"] == "employee" and assigned_to != current_user["id"]:
        return {"success": False, "error": "Forbidden: employee can create tasks only for themselves"}
    
    # Проверяем что assigned_to существует
    with db_cursor() as cur:
        cur.execute(q("SELECT id, name FROM users WHERE id = %s"), (assigned_to,))
        user_row = cur.fetchone()
        if not user_row:
            logger.error(f"[create_task] Ошибка: пользователь с id={assigned_to} не найден")
            return {"success": False, "error": f"Пользователь с id={assigned_to} не найден"}
        
        user_name = user_row[1]
        
        sql = """
            INSERT INTO tasks (assigned_to, created_by, lead_id, title, description, priority, due_date, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cur.execute(q(sql), (assigned_to, 'ai_agent', lead_id, title, description, priority, due, 'todo', 'manual', now))
        
        logger.info(f"[create_task] Создана задача '{title}' для {user_name} (id={assigned_to}), lead_id={lead_id}, priority={priority}")
        
    return {"success": True, "title": title, "assigned_to": assigned_to, "assigned_name": user_name, "due_date": due}


@tool(
    name="create_smart_task",
    description=(
        "Создать новую задачу с автоматическим определением исполнителя на основе загруженности команды. "
        "Агент сам выберет наименее загруженного сотрудника. "
        "Укажите title, priority (urgent/high/normal/low), и опционально lead_id."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Название задачи (обязательно)"
            },
            "description": {
                "type": "string",
                "description": "Описание задачи (опционально)"
            },
            "priority": {
                "type": "string",
                "enum": ["urgent", "high", "normal", "low"],
                "default": "normal",
                "description": "Приоритет задачи"
            },
            "lead_id": {
                "type": "integer",
                "description": "ID лида, если задача связана с конкретным лидом"
            },
            "task_type": {
                "type": "string",
                "enum": ["general", "call", "followup", "monitoring"],
                "default": "general",
                "description": "Тип задачи для лучшего подбора исполнителя"
            }
        },
        "required": ["title"]
    },
    roles=["admin", "manager", "employee"],
)
def create_smart_task(ctx, title: str, description: str = "", priority: str = "normal", lead_id: int | None = None, task_type: str = "general") -> dict:
    from db import q
    from services.legacy_tasks_notes import find_best_assignee_for_task
    from datetime import datetime, timedelta
    import logging
    
    logger = logging.getLogger("HHB_B2B")
    current_user = ctx["current_user"]


    # Умное распределение задачи
    best_assignee = find_best_assignee_for_task(priority, task_type)
    assigned_to = best_assignee['user_id'] if best_assignee else current_user["id"]

    # Security: employee может создавать задачи только для себя
    if current_user["role"] == "employee":
        assigned_to = current_user["id"]
    
    due = (datetime.now() + timedelta(hours=24)).isoformat()
    now = datetime.now().isoformat()
    
    sql = """
        INSERT INTO tasks (assigned_to, created_by, lead_id, title, description, priority, due_date, status, source, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    with db_cursor() as cur:
        cur.execute(q(sql), (assigned_to, current_user["username"], lead_id, title, description, priority, due, 'todo', 'ai_smart', now, now))
        
    assignee_name = best_assignee['username'] if best_assignee else current_user['username']
    load_info = f" (загруженность: {best_assignee['load_level']})" if best_assignee else ""
    
    logger.info(f"[create_smart_task] Создана задача '{title}' с умным распределением на {assignee_name}{load_info}")
    
    return {
        "success": True, 
        "title": title, 
        "assigned_to": assigned_to,
        "assignee_name": assignee_name,
        "load_level": best_assignee['load_level'] if best_assignee else 'unknown',
        "workload_score": best_assignee['workload_score'] if best_assignee else 0,
        "assignment_reason": f"Автоматически выбран наименее загруженный сотрудник{load_info}",
        "due_date": due
    }


@tool(
    name="get_team_workload",
    description=(
        "Получить текущую загруженность всей команды. "
        "Показывает количество задач, приоритеты и уровень загруженности каждого сотрудника."
    ),
    parameters={
        "type": "object",
        "properties": {},
    },
    roles=["admin", "manager"],
)
def get_team_workload(ctx) -> dict:
    from services.legacy_tasks_notes import get_team_workload
    
    team = get_team_workload()
    
    summary = {
        "total_employees": len(team),
        "critical_load": len([w for w in team if w['load_level'] == 'critical']),
        "high_load": len([w for w in team if w['load_level'] == 'high']),
        "medium_load": len([w for w in team if w['load_level'] == 'medium']),
        "low_load": len([w for w in team if w['load_level'] == 'low']),
        "team": team
    }
    
    return summary


@tool(
    name="complete_task",
    description=(
        "Отметить задачу как выполненную по её ID."
    ),
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "integer",
                "description": "ID задачи"
            }
        },
        "required": ["task_id"]
    },
    roles=["admin", "manager", "employee"],
)
def complete_task(ctx, task_id: int) -> dict:
    from db import q
    from datetime import datetime
    current_user = ctx["current_user"]
    now = datetime.now().isoformat()
    
    # Сначала проверяем существование и права
    check_sql = "SELECT id FROM tasks WHERE id = %s"
    params = [task_id]
    if current_user["role"] == "employee":
        check_sql += " AND assigned_to = %s"
        params.append(current_user["id"])
        
    with db_cursor() as cur:
        cur.execute(q(check_sql), tuple(params))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Задача не найдена или принадлежит другому пользователю"}
            
        cur.execute(q("UPDATE tasks SET status = 'done', completed_at = %s WHERE id = %s"), (now, task_id))
        
    return {"success": True, "task_id": task_id, "status": "done"}


def find_best_assignee_for_task(priority: str, task_type: str) -> dict | None:
    """
    Находит наименее загруженного сотрудника для назначения задачи.
    Возвращает словарь с user_id и user_name или None если не найден.
    """
    from db import db_cursor, q
    from datetime import datetime, timedelta
    import logging
    
    logger = logging.getLogger("HHB_B2B")
    
    try:
        with db_cursor() as cur:
            # Получаем всех активных сотрудников
            cur.execute(q("SELECT id, name FROM users WHERE role IN ('employee', 'manager') ORDER BY id"))
            users = cur.fetchall()
            
            if not users:
                return None
            
            # Считаем активные задачи у каждого
            best_user = None
            min_tasks = float('inf')
            
            for user_id, user_name in users:
                cur.execute(q("""
                    SELECT COUNT(*) FROM tasks 
                    WHERE assigned_to = %s AND status IN ('todo', 'open', 'in_progress')
                """), (user_id,))
                task_count = cur.fetchone()[0]
                
                if task_count < min_tasks:
                    min_tasks = task_count
                    best_user = {"user_id": user_id, "user_name": user_name, "task_count": task_count}
            
            if best_user:
                logger.info(f"[find_best_assignee] Выбран {best_user['user_name']} (id={best_user['user_id']}) с {best_user['task_count']} задачами")
            
            return best_user
            
    except Exception as e:
        logger.error(f"[find_best_assignee] Ошибка: {e}")
        return None
