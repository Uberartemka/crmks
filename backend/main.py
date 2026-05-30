from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import uvicorn
import logging
import traceback
import urllib.request
import urllib.parse
import urllib.error
import json
import time
import os
from dotenv import load_dotenv
load_dotenv()
import smtplib
import sqlite3
import psycopg2
import hashlib
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader

# === CONFIGURE STANDARD SYSTEM LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler("D:/pod/backend/app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("HHB_B2B")

from queue_manager import QueueManager

# === Hybrid DB: PostgreSQL preferred, SQLite fallback for dev ===
PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")
SQLITE_PATH = os.getenv("SQLITE_PATH", "D:/pod/backend/catalog.db")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# === Jinja2 Templates ===
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

_use_pg = False

def _test_pg():
    global _use_pg
    try:
        conn = psycopg2.connect(PG_URL)
        conn.close()
        _use_pg = True
        logger.info("[Database] PostgreSQL доступен. Используем PG для каталога/КП.")
    except Exception:
        _use_pg = False
        logger.warning("[Database] PostgreSQL недоступен. Fallback на SQLite для каталога/КП.")

_test_pg()

def get_db():
    if _use_pg:
        return psycopg2.connect(PG_URL)
    else:
        return sqlite3.connect(SQLITE_PATH)

def q(sql):
    """Adapt SQL from PostgreSQL dialect to SQLite if needed."""
    if _use_pg:
        return sql
    return sql.replace('%s', '?').replace('ILIKE', 'LIKE').replace('RETURNING id', '')

def get_last_id(cursor):
    if _use_pg:
        return cursor.fetchone()[0]
    else:
        return cursor.lastrowid

def _ph(count):
    """Return placeholders for current DB driver."""
    if _use_pg:
        return ','.join(['%s'] * count)
    else:
        return ','.join(['?'] * count)

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    phash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}${phash}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, phash = stored.split('$', 1)
        check = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return check == phash
    except Exception:
        return False

# === KIMI (Moonshot AI) CLIENT ===

_kimi_client = None

def get_kimi_client():
    global _kimi_client
    if _kimi_client is None and OpenAI is not None:
        api_key = os.getenv("KIMI_API_KEY")
        if api_key:
            _kimi_client = OpenAI(
                api_key=api_key,
                base_url="https://api.moonshot.cn/v1",
            )
    return _kimi_client

# === AI TOOL REGISTRY ===

def _tool_find_user(query: str, current_user: dict):
    conn = get_db()
    cursor = conn.cursor()
    like = f"%{query}%"
    cursor.execute(q("""
        SELECT id, username, name, role FROM users
        WHERE name ILIKE %s OR username ILIKE %s
        ORDER BY name LIMIT 10
    """), (like, like))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "name": r[2], "role": r[3]} for r in rows]

def _tool_list_users(role_filter: Optional[str] = None, current_user: dict = None):
    conn = get_db()
    cursor = conn.cursor()
    if role_filter:
        cursor.execute(q("SELECT id, username, name, role FROM users WHERE role = %s ORDER BY name"), (role_filter,))
    else:
        cursor.execute(q("SELECT id, username, name, role FROM users ORDER BY name"))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "name": r[2], "role": r[3]} for r in rows]

def _tool_list_clients(search: Optional[str] = None, current_user: dict = None):
    conn = get_db()
    cursor = conn.cursor()
    if search:
        like = f"%{search}%"
        cursor.execute(q("""
            SELECT id, name, email, city, status, discount FROM clients
            WHERE name ILIKE %s OR email ILIKE %s OR city ILIKE %s
            ORDER BY name LIMIT 20
        """), (like, like, like))
    else:
        cursor.execute(q("SELECT id, name, email, city, status, discount FROM clients ORDER BY name LIMIT 20"))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "email": r[2], "city": r[3], "status": r[4], "discount": r[5]} for r in rows]

def _tool_list_tasks(status: Optional[str] = None, assigned_to: Optional[int] = None, current_user: dict = None):
    conn = get_db()
    cursor = conn.cursor()
    # Use tasks table if exists, otherwise employee_plans as fallback
    try:
        if status and assigned_to:
            cursor.execute(q("""
                SELECT id, title, description, status, priority, due_date, assigned_to FROM tasks
                WHERE status = %s AND assigned_to = %s ORDER BY due_date
            """), (status, assigned_to))
        elif status:
            cursor.execute(q("""
                SELECT id, title, description, status, priority, due_date, assigned_to FROM tasks
                WHERE status = %s ORDER BY due_date
            """), (status,))
        elif assigned_to:
            cursor.execute(q("""
                SELECT id, title, description, status, priority, due_date, assigned_to FROM tasks
                WHERE assigned_to = %s ORDER BY due_date
            """), (assigned_to,))
        else:
            cursor.execute(q("SELECT id, title, description, status, priority, due_date, assigned_to FROM tasks ORDER BY due_date"))
    except Exception:
        # Fallback: no tasks table yet
        conn.close()
        return []
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "status": r[3], "priority": r[4], "due_date": r[5], "assigned_to": r[6]} for r in rows]

def _tool_create_task(title: str, description: str = "", assignee_id: Optional[int] = None, priority: str = "medium", due_date: Optional[str] = None, current_user: dict = None):
    if current_user["role"] not in ("admin", "manager"):
        return {"error": "Forbidden: only admin or manager can create tasks"}
    # Manager can only assign to self unless admin
    if current_user["role"] == "manager" and assignee_id and assignee_id != current_user["id"]:
        return {"error": "Manager can only assign tasks to themselves"}
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        cursor.execute(q("""
            INSERT INTO tasks (title, description, status, priority, due_date, assigned_to, created_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """), (title, description, "todo", priority, due_date, assignee_id or current_user["id"], current_user["id"], now, now))
        tid = get_last_id(cursor)
        conn.commit()
        conn.close()
        return {"id": tid, "title": title, "status": "todo", "assigned_to": assignee_id or current_user["id"]}
    except Exception as e:
        conn.close()
        return {"error": str(e)}

def _tool_update_task_status(task_id: int, status: str, current_user: dict = None):
    if current_user["role"] not in ("admin", "manager"):
        return {"error": "Forbidden"}
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(q("UPDATE tasks SET status = %s, updated_at = %s WHERE id = %s"), (status, now, task_id))
    conn.commit()
    conn.close()
    return {"task_id": task_id, "status": status}

def _tool_assign_tasks_bulk(client_ids: List[int], manager_id: int, template: str = "", current_user: dict = None):
    if current_user["role"] != "admin":
        return {"error": "Only admin can bulk assign"}
    created = []
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    for cid in client_ids:
        cursor.execute(q("SELECT name FROM clients WHERE id = %s"), (cid,))
        row = cursor.fetchone()
        client_name = row[0] if row else f"Client #{cid}"
        title = template.replace("{client_name}", client_name) if template else f"Работа с {client_name}"
        try:
            cursor.execute(q("""
                INSERT INTO tasks (title, description, status, priority, assigned_to, created_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """), (title, "", "todo", "medium", manager_id, current_user["id"], now, now))
            tid = get_last_id(cursor)
            created.append({"task_id": tid, "client_id": cid, "title": title})
        except Exception as e:
            created.append({"client_id": cid, "error": str(e)})
    conn.commit()
    conn.close()
    return {"created": created}

def _tool_prepare_document(doc_type: str, client_id: Optional[int] = None, current_user: dict = None):
    return {"status": "queued", "doc_type": doc_type, "client_id": client_id, "preview_url": None}

TOOL_REGISTRY = {
    "find_user": _tool_find_user,
    "list_users": _tool_list_users,
    "list_clients": _tool_list_clients,
    "list_tasks": _tool_list_tasks,
    "create_task": _tool_create_task,
    "update_task_status": _tool_update_task_status,
    "assign_tasks_bulk": _tool_assign_tasks_bulk,
    "prepare_document": _tool_prepare_document,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "find_user",
            "description": "Найти пользователя (сотрудника, менеджера, клиента) по имени, email или фрагменту",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Имя, email или фрагмент для поиска"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_users",
            "description": "Получить список пользователей. Можно фильтровать по роли.",
            "parameters": {
                "type": "object",
                "properties": {"role_filter": {"type": "string", "enum": ["admin", "manager", "employee", "client"], "description": "Фильтр по роли"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_clients",
            "description": "Получить список клиентов или найти по названию/городу",
            "parameters": {
                "type": "object",
                "properties": {"search": {"type": "string", "description": "Поиск по названию, email или городу"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Получить список задач с фильтрами",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"]},
                    "assigned_to": {"type": "integer", "description": "ID исполнителя"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Создать новую задачу. Админ может назначить любому, менеджер — только себе.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "assignee_id": {"type": "integer", "description": "ID исполнителя. Если не указан — себе."},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "due_date": {"type": "string", "description": "ISO 8601 datetime"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": "Обновить статус задачи",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"]},
                },
                "required": ["task_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_tasks_bulk",
            "description": "Пакетное создание задач для нескольких клиентов (только админ)",
            "parameters": {
                "type": "object",
                "properties": {
                    "client_ids": {"type": "array", "items": {"type": "integer"}},
                    "manager_id": {"type": "integer"},
                    "template": {"type": "string", "description": "Шаблон названия задачи, {client_name}"},
                },
                "required": ["client_ids", "manager_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_document",
            "description": "Подготовить документ (ТЭО, КП, аудит)",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {"type": "string", "enum": ["teo", "kp", "audit"]},
                    "client_id": {"type": "integer"},
                },
                "required": ["doc_type"],
            },
        },
    },
]

# === AGENT LOOP ===

def run_kimi_agent(messages: List[Dict[str, str]], current_user: dict, max_rounds: int = 10):
    client = get_kimi_client()
    if not client:
        raise HTTPException(status_code=500, detail="Kimi client not configured")

    system_prompt = (
        "Ты — AI-ассистент админ-панели HHB (B2B дистрибьютор подшипников). "
        "У тебя есть доступ к БД через инструменты. "
        "Правила:\n"
        "- Если пользователь упоминает имя — сначала find_user, не угадывай ID\n"
        "- Если нашёл несколько совпадений — переспроси кого именно\n"
        "- Перед массовыми действиями — подтверди план одной фразой\n"
        "- После выполнения — кратко отчитайся: 'Готово, задача #142 назначена Ивану'\n"
        "- Не выдумывай ID, статусы, даты — только из реальных tool-результатов\n"
        "- На русском, по-деловому, без воды"
    )

    # Inject system prompt
    chat_messages = [{"role": "system", "content": system_prompt}]
    for m in messages:
        if m.get("role") in ("user", "assistant", "tool"):
            chat_messages.append({"role": m["role"], "content": m.get("content", "")})

    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=chat_messages,
            tools=TOOL_DEFINITIONS,
            temperature=0.3,
        )

        choice = response.choices[0]
        msg = choice.message

        # If no tool calls, return the response
        if not msg.tool_calls:
            return {
                "id": str(int(time.time())),
                "role": "assistant",
                "content": msg.content or "",
                "created_at": datetime.now().isoformat(),
            }

        # Execute tool calls
        assistant_msg = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = []
            for tc in msg.tool_calls:
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
        chat_messages.append(assistant_msg)

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}

            if tool_name in TOOL_REGISTRY:
                tool_fn = TOOL_REGISTRY[tool_name]
                try:
                    result = tool_fn(**args, current_user=current_user)
                except TypeError:
                    # Remove current_user if tool doesn't accept it
                    result = tool_fn(**args)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            chat_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # Max rounds exceeded
    return {
        "id": str(int(time.time())),
        "role": "assistant",
        "content": "Достигнут лимит итераций. Попробуйте уточнить запрос.",
        "created_at": datetime.now().isoformat(),
    }

def init_catalog_tables():
    """Initialize SKU catalog, clients, proposals and proposal_items tables."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if _use_pg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sku_catalog (
                    id SERIAL PRIMARY KEY,
                    sku VARCHAR(200) NOT NULL UNIQUE,
                    category VARCHAR(100), gost VARCHAR(50),
                    d_inner NUMERIC(10,2), d_outer NUMERIC(10,2), b_width NUMERIC(10,2),
                    type VARCHAR(300), brand VARCHAR(50), stock VARCHAR(100),
                    price NUMERIC(12,2) NOT NULL DEFAULT 0,
                    img VARCHAR(300), created_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(300) NOT NULL, bitrix_id VARCHAR(100),
                    email VARCHAR(300), city VARCHAR(100),
                    discount INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active', created_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    title VARCHAR(300), total_amount NUMERIC(14,2) DEFAULT 0,
                    discount_global INTEGER DEFAULT 0, status VARCHAR(50) DEFAULT 'draft',
                    email_sent BOOLEAN DEFAULT FALSE,
                    created_at VARCHAR(100), updated_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposal_items (
                    id SERIAL PRIMARY KEY,
                    proposal_id INTEGER REFERENCES proposals(id) ON DELETE CASCADE,
                    sku_id INTEGER REFERENCES sku_catalog(id) ON DELETE CASCADE,
                    qty INTEGER NOT NULL DEFAULT 1,
                    price_base NUMERIC(12,2) NOT NULL DEFAULT 0,
                    discount_item INTEGER DEFAULT 0,
                    price_final NUMERIC(12,2) NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(256) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    role VARCHAR(50) NOT NULL DEFAULT 'employee',
                    created_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_plans (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    calls_target INTEGER NOT NULL DEFAULT 0,
                    registrations_target INTEGER NOT NULL DEFAULT 0,
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100),
                    UNIQUE(user_id, month, year)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS call_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    lead_id INTEGER REFERENCES parsed_leads(id) ON DELETE SET NULL,
                    client_name VARCHAR(300),
                    from_number VARCHAR(50),
                    to_number VARCHAR(50),
                    direction VARCHAR(20) DEFAULT 'outgoing',
                    call_date VARCHAR(50),
                    status VARCHAR(50),
                    duration INTEGER DEFAULT 0,
                    recording_url TEXT,
                    notes TEXT,
                    is_new_registration BOOLEAN DEFAULT FALSE,
                    bitrix_call_id VARCHAR(100),
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS parsed_leads (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(300) NOT NULL,
                    category VARCHAR(200),
                    city VARCHAR(100),
                    contacts TEXT,
                    need_description TEXT,
                    query VARCHAR(200),
                    region VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'new',
                    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    call_count INTEGER DEFAULT 0,
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    description TEXT,
                    kind VARCHAR(50) DEFAULT 'meeting',
                    start TIMESTAMP NOT NULL,
                    "end" TIMESTAMP,
                    all_day BOOLEAN DEFAULT FALSE,
                    location VARCHAR(300),
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    color VARCHAR(20) DEFAULT 'blue',
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    description TEXT,
                    status VARCHAR(50) DEFAULT 'todo',
                    priority VARCHAR(20) DEFAULT 'medium',
                    due_date VARCHAR(100),
                    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100)
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sku_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL UNIQUE,
                    category TEXT, gost TEXT,
                    d_inner REAL, d_outer REAL, b_width REAL,
                    type TEXT, brand TEXT, stock TEXT,
                    price REAL NOT NULL DEFAULT 0,
                    img TEXT, created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, bitrix_id TEXT,
                    email TEXT, city TEXT,
                    discount INTEGER NOT NULL DEFAULT 0,
                    status TEXT DEFAULT 'active', created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    kind TEXT DEFAULT 'meeting',
                    start TEXT NOT NULL,
                    "end" TEXT,
                    all_day INTEGER DEFAULT 0,
                    location TEXT,
                    client_id INTEGER,
                    color TEXT DEFAULT 'blue',
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'todo',
                    priority TEXT DEFAULT 'medium',
                    due_date TEXT,
                    assigned_to INTEGER,
                    created_by INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    created_by INTEGER,
                    title TEXT, total_amount REAL DEFAULT 0,
                    discount_global INTEGER DEFAULT 0, status TEXT DEFAULT 'draft',
                    email_sent INTEGER DEFAULT 0,
                    created_at TEXT, updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proposal_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER,
                    sku_id INTEGER,
                    qty INTEGER NOT NULL DEFAULT 1,
                    price_base REAL NOT NULL DEFAULT 0,
                    discount_item INTEGER DEFAULT 0,
                    price_final REAL NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'employee',
                    created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    month INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    calls_target INTEGER NOT NULL DEFAULT 0,
                    registrations_target INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, month, year)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS call_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    client_id INTEGER,
                    lead_id INTEGER,
                    client_name TEXT,
                    from_number TEXT,
                    to_number TEXT,
                    direction TEXT DEFAULT 'outgoing',
                    call_date TEXT,
                    status TEXT,
                    duration INTEGER DEFAULT 0,
                    recording_url TEXT,
                    notes TEXT,
                    is_new_registration INTEGER DEFAULT 0,
                    bitrix_call_id TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS parsed_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT,
                    city TEXT,
                    contacts TEXT,
                    need_description TEXT,
                    query TEXT,
                    region TEXT,
                    status TEXT DEFAULT 'new',
                    assigned_to INTEGER,
                    call_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
        conn.commit()
        logger.info("[Database] Таблицы КП, каталога и клиентов инициализированы.")
        conn.close()
    except Exception as e:
        logger.error(f"[!] [Database Error] Ошибка инициализации каталога/КП: {e}")

init_catalog_tables()

def migrate_call_logs_columns():
    """Add missing columns to existing call_logs table."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        new_cols = [
            ('lead_id', 'INTEGER'),
            ('from_number', 'TEXT' if not _use_pg else 'VARCHAR(50)'),
            ('to_number', 'TEXT' if not _use_pg else 'VARCHAR(50)'),
            ('direction', 'TEXT' if not _use_pg else 'VARCHAR(20)'),
            ('duration', 'INTEGER'),
            ('recording_url', 'TEXT'),
            ('bitrix_call_id', 'TEXT' if not _use_pg else 'VARCHAR(100)'),
            ('updated_at', 'TEXT' if not _use_pg else 'VARCHAR(100)'),
        ]
        for col, col_type in new_cols:
            try:
                if _use_pg:
                    cursor.execute(f"ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS {col} {col_type}")
                else:
                    cursor.execute(f"ALTER TABLE call_logs ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # column likely already exists
        conn.commit()
        conn.close()
        logger.info("[Database] Миграция call_logs выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция call_logs: {e}")

migrate_call_logs_columns()

def migrate_proposals_columns():
    """Add missing columns to existing proposals table."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if _use_pg:
            cursor.execute("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS created_by INTEGER")
        else:
            try:
                cursor.execute("ALTER TABLE proposals ADD COLUMN created_by INTEGER")
            except Exception:
                pass
        conn.commit()
        conn.close()
        logger.info("[Database] Миграция proposals выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция proposals: {e}")

migrate_proposals_columns()

# === Seed Data (one-time load if tables empty) ===
def seed_data():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sku_catalog")
        if cursor.fetchone()[0] == 0:
            skus = [
                ('HHB UCP 206', 'housing', '480206', 30, 62, 38.1, 'Корпусной узел на лапах (Pillow Block)', 'HHB', 'Достаточно', 1180, 'images/ucp.jpg'),
                ('HHB UCF 208', 'housing', '480208', 40, 80, 49.2, 'Квадратный фланцевый узел (Flange Block)', 'HHB', 'Достаточно', 1420, 'images/ucf.jpg'),
                ('HHB UCFL 205', 'housing', '480205', 25, 52, 34.1, 'Ромбический фланцевый узел (2-bolt Flange)', 'HHB', 'Достаточно', 980, 'images/ucfl.jpg'),
                ('HHB UCT 207', 'housing', '480207', 35, 72, 42.9, 'Натяжной узел для нории (Take-up Unit)', 'HHB', 'В наличии', 1850, 'images/uct.jpg'),
                ('HHB STAINLESS UC 204', 'stainless', 'SS480204', 20, 47, 31, 'Нержавеющая сталь (Stainless Series)', 'HHB', '18 шт', 2950, 'images/stainless.jpg'),
                ('FKD UK 208 + H2308', 'housing', 'UK208', 35, 80, 49, 'С конической закрепительной втулкой', 'FKD', '95 шт', 1620, 'images/uk.jpg'),
                ('FKD NA 206', 'housing', 'NA206', 30, 62, 36.4, 'С эксцентриковым стопорным кольцом', 'FKD', 'Достаточно', 730, 'images/na.jpg'),
                ('HHB 22315-E1-T41A', 'roller', '3615', 75, 160, 55, 'Сферический роликовый для виброгрохотов', 'HHB', '12 шт', 7950, 'images/spherical.jpg'),
                ('HHB 6205-2RS C3', 'ball', '180205', 25, 52, 15, 'Радиальный шариковый с увеличенным зазором', 'HHB', '1 240 шт', 420, 'frames_eevee/mobile_webp/0060.webp'),
                ('HHB 6206-2RS C3', 'ball', '180206', 30, 62, 16, 'Радиальный шариковый с зазором C3', 'HHB', '850 шт', 540, 'frames_eevee/mobile_webp/0060.webp'),
                ('FKD UC 210', 'housing', '480210', 50, 90, 51.6, 'Шариковый радиальный под закрепительный винт', 'FKD', '320 шт', 690, 'images/ucp.jpg'),
                ('Сальник 30х52х10 (Манжета)', 'cuffs', '8752-79', 30, 52, 10, 'Армированная одновальная манжета ГОСТ', 'FKD', 'Достаточно', 180, 'frames_eevee/mobile_webp/0060.webp'),
                ('HHB NU 312 ECP', 'roller', '12312', 60, 130, 31, 'Цилиндрический роликовый', 'HHB', '45 шт', 4300, 'images/roller.jpg'),
                ('HHB 6308-2RS', 'ball', '180308', 40, 90, 23, 'Радиальный шариковый однорядный', 'HHB', '560 шт', 890, 'images/ball.jpg'),
                ('FKD UCP 209', 'housing', '480209', 45, 85, 49.2, 'Корпусной узел на лапах', 'FKD', '120 шт', 1050, 'images/ucp.jpg'),
            ]
            now = datetime.now().isoformat()
            skus = [sku + (now,) for sku in skus]
            cursor.executemany(f"""
                INSERT INTO sku_catalog (sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img, created_at)
                VALUES ({_ph(12)})
            """, skus)
            logger.info(f"[Seed] Загружено {len(skus)} SKU в каталог.")

        cursor.execute("SELECT COUNT(*) FROM clients")
        if cursor.fetchone()[0] == 0:
            clients = [
                ('ООО "АГРОЭКО"', 'BX_1245', 'snab@agroeco.ru', 'Воронеж', 15, 'active'),
                ('ООО "ЭКОНИВА-ЧЕРНОЗЕМЬЕ"', 'BX_3312', 'zakup@econiva.ru', 'Воронеж', 10, 'active'),
                ('АПХ "МИРАТОРГ"', 'BX_8821', 'supply@miratorg.ru', 'Орёл', 5, 'active'),
                ('ГК "РУСАГРО"', 'BX_9901', 'tender@rusagro.ru', 'Москва', 0, 'new'),
                ('ООО "Воронежский Элеватор"', 'BX_1122', 'main@vorelev.ru', 'Воронеж', 20, 'vip'),
            ]
            now = datetime.now().isoformat()
            clients = [client + (now,) for client in clients]
            cursor.executemany(f"""
                INSERT INTO clients (name, bitrix_id, email, city, discount, status, created_at)
                VALUES ({_ph(7)})
            """, clients)
            logger.info(f"[Seed] Загружено {len(clients)} клиентов.")

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            now = datetime.now().isoformat()
            users = [
                ('admin', hash_password('admin123'), 'Администратор', 'admin', now),
                ('manager1', hash_password('pass123'), 'Иванов Иван', 'manager', now),
                ('emp1', hash_password('pass123'), 'Петрова Анна', 'employee', now),
                ('emp2', hash_password('pass123'), 'Сидоров Пётр', 'employee', now),
            ]
            cursor.executemany(f"""
                INSERT INTO users (username, password_hash, name, role, created_at)
                VALUES ({_ph(5)})
            """, users)
            logger.info(f"[Seed] Загружено {len(users)} пользователей.")

        cursor.execute("SELECT COUNT(*) FROM parsed_leads")
        if cursor.fetchone()[0] == 0:
            now = datetime.now().isoformat()
            leads = [
                ('Воронежский Мукомольный Комбинат', 'Элеватор, Хранение', 'Воронеж', '+7 (473) 255-44-12 · vormuk.ru', 'Корпусные узлы UCP208 для приводных барабанов норий. Высокая агропыль.', 'элеватор', 'Воронеж', now, now),
                ('АГРОЭКО-Восток (Элеваторный Хаб)', 'Элеватор, Зернохранилище', 'Воронеж', '+7 (473) 200-11-11 · agroeco.ru', 'Самоустанавливающиеся подшипники серии UC, натяжные узлы UCF206.', 'элеватор', 'Воронеж', now, now),
                ('Калачеевский Элеватор', 'Элеватор, Сушилки', 'Калач', '+7 (47363) 2-14-55 · kalachel.ru', 'Двухрядные сферические подшипники для вентиляторов зерносушилок.', 'элеватор', 'Воронеж', now, now),
                ('Липецкхлебмакаронпром', 'Элеватор, Мельница', 'Липецк', '+7 (4742) 28-04-12 · lhm.ru', 'Премиум подшипники HHB 6205, зазор C3, радиальные.', 'элеватор', 'Липецк', now, now),
                ('Грибановский Сахарный Завод', 'Сахарный завод, Пищевка', 'Грибановка', '+7 (47348) 3-01-22', 'Подшипники конвейерной ленты сырого жома, нержавеющие корпуса HHB-SS.', 'сахарный завод', 'Воронеж', now, now),
                ('Павловск Неруд (Карьероуправление)', 'Добыча щебня, Карьер', 'Павловск', '+7 (47362) 2-15-51 · pavlovskgranit.ru', 'Вибростойкие подшипники HHB T41A (22316) для инерционных грохотов. Ударная нагрузка.', 'карьер', 'Воронеж', now, now),
            ]
            cursor.executemany(f"""
                INSERT INTO parsed_leads (name, category, city, contacts, need_description, query, region, created_at, updated_at)
                VALUES ({_ph(9)})
            """, leads)
            logger.info(f"[Seed] Загружено {len(leads)} лидов парсера.")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[!] [Seed Error] Ошибка загрузки seed-данных: {e}")

seed_data()

# === FastAPI Web Server with Integrated Task Queue ===

app = FastAPI(
    title="HHB / FKD B2B Integration Backend",
    description="Отказоустойчивый сервер обработки очередей задач (1С, Битрикс24, Генерация счетов)",
    version="2.0.0"
)

# Enable CORS for local testing on frontend (index.html, admin.html, employee.html)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === IN-MEMORY TOKEN BUCKET RATE LIMITER ===
# Sliding window rate limiter to protect resources from brute-force/DDOS (No Redis needed!)
rate_limit_records = defaultdict(list)

def get_rate_limit(path: str) -> int:
    if "/api/ai/search" in path:
        return 10  # Max 10 search queries per minute
    if "/api/queue/add" in path:
        return 20  # Max 20 new tasks per minute
    if "/api/webhooks/" in path:
        return 30  # Max 30 incoming webhooks per minute
    return 60      # Default: 60 requests per minute for other endpoints

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    # Skip docs, redoc, openapi.json and root paths
    path = request.url.path
    if path in ["/", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    limit = get_rate_limit(path)
    now = time.time()
    
    # Unique key combining IP and path category
    key = f"{client_ip}:{path}"
    
    # Cleanup timestamps older than 60 seconds
    rate_limit_records[key] = [t for t in rate_limit_records[key] if now - t < 60]
    
    if len(rate_limit_records[key]) >= limit:
        logger.warning(f"[Rate Limit Blocked] IP {client_ip} превысил лимит на {path} ({limit} запр./мин).")
        return Response(
            content=json.dumps({"detail": "Too Many Requests. Вы превысили лимит запросов для этого эндпоинта. Попробуйте позже."}),
            status_code=429,
            media_type="application/json",
            headers={"Retry-After": "60"}
        )
        
    rate_limit_records[key].append(now)
    return await call_next(request)

# === SECURE BEARER TOKEN AUTHORIZATION DEPENDENCY ===
B2B_ADMIN_TOKEN = os.getenv("B2B_ADMIN_TOKEN", "hhb_b2b_secret_token_2026")

def verify_b2b_token(request: Request):
    # Allow local Swagger UI testing to bypass authorization easily if wanted
    # But strictly enforce on real requests
    auth_header = request.headers.get("Authorization") or request.headers.get("X-API-Key")
    
    token = None
    if auth_header:
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = auth_header

    if token != B2B_ADMIN_TOKEN:
        logger.warning(f"[Auth Failed] Неавторизованный запрос к {request.url.path} с IP {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=401, detail="Unauthorized. Неверный или отсутствующий API-токен авторизации B2B.")
    return token

# === USER AUTHENTICATION SYSTEM ===
active_tokens: Dict[str, int] = {}

class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str = 'employee'

class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str

class PlanCreate(BaseModel):
    user_id: int
    month: int
    year: int
    calls_target: int = 0
    registrations_target: int = 0

class CallLogCreate(BaseModel):
    client_id: Optional[int] = None
    lead_id: Optional[int] = None
    client_name: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    direction: Optional[str] = 'outgoing'
    call_date: str
    status: str = 'scheduled'
    duration: Optional[int] = 0
    recording_url: Optional[str] = None
    notes: str = ''
    is_new_registration: bool = False
    bitrix_call_id: Optional[str] = None

class CallLogOut(BaseModel):
    id: int
    user_id: int
    client_id: Optional[int]
    lead_id: Optional[int]
    client_name: str
    from_number: Optional[str]
    to_number: Optional[str]
    direction: Optional[str]
    call_date: str
    status: str
    duration: Optional[int]
    recording_url: Optional[str]
    notes: str
    is_new_registration: bool
    bitrix_call_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    city: Optional[str] = None
    bitrix_id: Optional[str] = None
    discount: int = 0

class CalendarEventIn(BaseModel):
    title: str
    description: Optional[str] = None
    kind: str = 'meeting'
    start: datetime
    end: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    client_id: Optional[int] = None
    color: str = 'blue'

class LeadOut(BaseModel):
    id: int
    name: str
    category: Optional[str]
    city: Optional[str]
    contacts: Optional[str]
    need_description: Optional[str]
    query: Optional[str]
    region: Optional[str]
    status: str
    assigned_to: Optional[int]
    assigned_name: Optional[str]
    call_count: int
    created_at: Optional[str]

class LeadAssign(BaseModel):
    user_id: Optional[int]

class LeadStatusUpdate(BaseModel):
    status: str

class DailyPlanItem(BaseModel):
    user_id: int
    user_name: str
    calls_target: int
    daily_calls: int
    assigned_leads: int
    completed_calls: int
    remaining_calls: int

def get_current_user(request: Request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Unauthorized')
    token = auth_header[7:]
    user_id = active_tokens.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT id, username, name, role FROM users WHERE id = %s"), (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail='User not found')
    return {'id': row[0], 'username': row[1], 'name': row[2], 'role': row[3]}

# Instantiate queue manager and start worker thread on server boot
logger.info("[Server] Инициализация менеджера очередей задач...")
qm = None
if _use_pg:
    qm = QueueManager()
    qm.start_worker()
else:
    logger.warning("[Queue] PostgreSQL недоступен. Очередь задач отключена для локального SQLite-режима.")

def get_queue_manager():
    if qm is None:
        raise HTTPException(status_code=503, detail="Очередь задач недоступна: PostgreSQL не запущен. КП, каталог и клиенты работают в локальном SQLite-режиме.")
    return qm

class TaskInput(BaseModel):
    task_type: str
    payload: Dict[str, Any]
    max_retries: int = 3

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "HHB B2B Integration Queue",
        "endpoints": {
            "swagger": "/docs",
            "add_task": "POST /api/queue/add",
            "list_tasks": "GET /api/queue/list",
            "stats": "GET /api/queue/stats"
        }
    }

@app.post("/api/queue/add")
def add_task(input_data: TaskInput):
    valid_types = ["1c_sync", "crm_lead", "email_invoice"]
    if input_data.task_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Невалидный тип задачи. Допустимые: {valid_types}")
        
    manager = get_queue_manager()
    task_id = manager.add_task(input_data.task_type, input_data.payload, input_data.max_retries)
    return {"status": "added", "task_id": task_id, "detail": "Задача успешно добавлена в очередь на обработку."}

@app.get("/api/queue/status/{task_id}")
def get_task_status(task_id: int):
    manager = get_queue_manager()
    status = manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Задача с таким ID не найдена в базе данных.")
    return status

@app.get("/api/queue/list", dependencies=[Depends(verify_b2b_token)])
def list_tasks():
    manager = get_queue_manager()
    return manager.list_tasks(limit=50)

@app.get("/api/queue/stats", dependencies=[Depends(verify_b2b_token)])
def get_stats():
    manager = get_queue_manager()
    return manager.get_queue_stats()

@app.post("/api/queue/retry/{task_id}", dependencies=[Depends(verify_b2b_token)])
def retry_task(task_id: int):
    manager = get_queue_manager()
    status = manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    if status["status"] != "failed":
        raise HTTPException(status_code=400, detail="Перезапустить можно только задачи со статусом 'failed'.")
        
    manager.retry_task(task_id)
    return {"status": "queued", "task_id": task_id, "detail": "Задача возвращена в статус 'pending' на повторную обработку."}

# === WEBHOOK ENDPOINTS (PUSH INTEGRATIONS) ===

class BitrixWebhookInput(BaseModel):
    event: str
    data: Dict[str, Any]

class OneCWebhookInput(BaseModel):
    sku: str
    new_stock: int
    new_price: float

class AiSearchRequest(BaseModel):
    query: str
    api_key: Optional[str] = None

class AiChatMessage(BaseModel):
    role: str
    content: str

class AiChatRequest(BaseModel):
    messages: List[AiChatMessage]
    tools: Optional[List[Dict[str, Any]]] = None
    tool_results: Optional[List[Dict[str, Any]]] = None

@app.post("/api/webhooks/bitrix", dependencies=[Depends(verify_b2b_token)])
def bitrix_webhook(payload: BitrixWebhookInput):
    logger.info(f"[Webhook] Получено событие от Битрикс24: {payload.event}")
    
    # Process event payload (e.g. Lead update, Deal close)
    deal_id = payload.data.get("FIELDS", {}).get("ID") or payload.data.get("ID")
    task_payload = {
        "event_type": payload.event,
        "deal_id": deal_id,
        "raw_data": payload.data
    }
    
    # Queue task asynchronously so Bitrix gets immediate 200 OK reply
    manager = get_queue_manager()
    task_id = manager.add_task("crm_lead", task_payload, max_retries=3)
    return {
        "status": "received",
        "event_processed": payload.event,
        "task_id": task_id,
        "detail": "Событие Битрикс24 зарегистрировано и добавлено в асинхронную очередь воркера."
    }

# === BITRIX TELEPHONY WEBHOOKS ===
class BitrixTelephonyInput(BaseModel):
    event: str  # e.g. ONVOXIMPLANTCALLSTART, ONVOXIMPLANTCALLEND
    data: Dict[str, Any]

@app.post("/api/webhooks/bitrix/telephony")
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

    # Map Bitrix status to our status
    status_map = {
        "success": "completed",
        "failed": "no_answer",
        "declined": "rejected",
        "missed": "no_answer",
        "busy": "no_answer",
        "not_available": "no_answer",
        " congestion": "no_answer",
    }
    mapped_status = status_map.get(str(status).lower(), str(status).lower())

    # Find lead by phone number or CRM entity
    lead_id = None
    client_name = "Unknown"
    conn = get_db()
    cursor = conn.cursor()
    try:
        if crm_entity_type == "LEAD" and crm_entity_id:
            cursor.execute(q("SELECT id, name FROM parsed_leads WHERE id = %s"), (crm_entity_id,))
        elif phone_number:
            # Normalize phone: keep only digits for matching
            digits = "".join(c for c in str(phone_number) if c.isdigit())
            if _use_pg:
                cursor.execute("SELECT id, name FROM parsed_leads WHERE REGEXP_REPLACE(contacts, '[^0-9]', '', 'g') LIKE %s LIMIT 1", ("%" + digits + "%",))
            else:
                cursor.execute("SELECT id, name FROM parsed_leads WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(contacts, '+', ''), '-', ''), '(', ''), ')', ''), ' ', '') LIKE ? LIMIT 1", ("%" + digits + "%",))
        row = cursor.fetchone()
        if row:
            lead_id = row[0]
            client_name = row[1]
    except Exception as e:
        logger.warning(f"[BitrixTelephony] Lead lookup failed: {e}")

    # Upsert call log
    try:
        cursor.execute(q("SELECT id FROM call_logs WHERE bitrix_call_id = %s"), (str(call_id),))
        existing = cursor.fetchone()
        now = datetime.now().isoformat()
        if existing:
            cursor.execute(q("""
                UPDATE call_logs SET status = %s, duration = %s, recording_url = %s,
                    to_number = %s, direction = %s, updated_at = %s
                WHERE bitrix_call_id = %s
            """), (mapped_status, int(duration) if duration else 0, record_url,
                   str(phone_number), str(direction).lower(), now, str(call_id)))
        else:
            cursor.execute(q("""
                INSERT INTO call_logs (user_id, lead_id, client_name, to_number, direction,
                    call_date, status, duration, recording_url, bitrix_call_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """), (user_id, lead_id, client_name, str(phone_number), str(direction).lower(),
                   now[:10], mapped_status, int(duration) if duration else 0, record_url,
                   str(call_id), now, now))
        conn.commit()
        logger.info(f"[BitrixTelephony] Call {call_id} logged/updated: status={mapped_status} duration={duration}")
    except Exception as e:
        logger.error(f"[!] [BitrixTelephony] Error saving call log: {e}")
        logger.error(traceback.format_exc())
    finally:
        conn.close()

    return {"status": "received", "event": payload.event, "call_id": call_id}

@app.post("/api/webhooks/1c", dependencies=[Depends(verify_b2b_token)])
def one_c_webhook(payload: OneCWebhookInput):
    logger.info(f"[Webhook] Получено обновление остатков из 1С для артикула: {payload.sku}")
    
    task_payload = {
        "sku": payload.sku,
        "new_stock": payload.new_stock,
        "new_price": payload.new_price
    }
    
    # Queue heavy inventory update asynchronously
    manager = get_queue_manager()
    task_id = manager.add_task("1c_sync", task_payload, max_retries=3)
    return {
        "status": "received",
        "sku_updated": payload.sku,
        "task_id": task_id,
        "detail": "Запрос обновления номенклатуры из 1С принят и поставлен в очередь задач."
    }

# ============================================================================
# === CATALOG, CLIENTS & PROPOSAL (КП) API ===
# ============================================================================

class SkuInput(BaseModel):
    sku: str
    category: Optional[str] = ""
    gost: Optional[str] = ""
    d: Optional[float] = None
    D: Optional[float] = None
    B: Optional[float] = None
    type: Optional[str] = ""
    brand: Optional[str] = ""
    stock: Optional[str] = ""
    price: float = 0
    img: Optional[str] = ""

class ProposalInput(BaseModel):
    client_id: int
    title: Optional[str] = ""
    discount_global: int = 0

class ProposalItemInput(BaseModel):
    sku_id: int
    qty: int = 1
    discount_item: int = 0

class SendEmailInput(BaseModel):
    recipient_email: Optional[str] = None
    subject: Optional[str] = "Коммерческое предложение HHB / FKD"

class DiscountInput(BaseModel):
    discount_global: int = 0

def recalc_proposal_total(proposal_id: int):
    """Recalculate total amount for a proposal based on its items."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT discount_global FROM proposals WHERE id = %s"), (proposal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    global_discount = row[0]
    cursor.execute(q("""
        SELECT qty, price_base, discount_item FROM proposal_items WHERE proposal_id = %s
    """), (proposal_id,))
    total = 0
    for qty, price_base, discount_item in cursor.fetchall():
        # Apply item discount first, then global discount
        price_after_item = float(price_base) * (1 - int(discount_item) / 100)
        price_after_global = price_after_item * (1 - int(global_discount) / 100)
        total += price_after_global * int(qty)
    cursor.execute(q("UPDATE proposals SET total_amount = %s, updated_at = %s WHERE id = %s"),
                   (total, datetime.now().isoformat(), proposal_id))
    conn.commit()
    conn.close()

# === SKU CATALOG ENDPOINTS ===

@app.get("/api/catalog/skus")
def list_skus(category: Optional[str] = None, search: Optional[str] = None, d_min: Optional[float] = None, d_max: Optional[float] = None):
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT id, sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img FROM sku_catalog WHERE 1=1"
    params = []
    if category and category != 'all':
        query += " AND category = %s"
        params.append(category)
    if search:
        query += " AND (sku ILIKE %s OR type ILIKE %s OR gost ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if d_min is not None:
        query += " AND d_inner >= %s"
        params.append(d_min)
    if d_max is not None:
        query += " AND d_inner <= %s"
        params.append(d_max)
    query += " ORDER BY id ASC"
    cursor.execute(q(query), params)
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "sku": r[1], "category": r[2], "gost": r[3], "d": float(r[4]) if r[4] else None,
             "D": float(r[5]) if r[5] else None, "B": float(r[6]) if r[6] else None,
             "type": r[7], "brand": r[8], "stock": r[9], "price": float(r[10]) if r[10] else 0, "img": r[11]} for r in rows]

@app.post("/api/catalog/skus", dependencies=[Depends(verify_b2b_token)])
def add_sku(data: SkuInput):
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(q("""
            INSERT INTO sku_catalog (sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """), (data.sku, data.category, data.gost, data.d, data.D, data.B, data.type, data.brand, data.stock, data.price, data.img, now))
        sku_id = get_last_id(cursor)
        conn.commit()
        conn.close()
        logger.info(f"[Catalog] Добавлен SKU #{sku_id}: {data.sku}")
        return {"status": "created", "sku_id": sku_id}
    except psycopg2.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="SKU с таким артикулом уже существует.")

# === CLIENTS ENDPOINTS ===

@app.get("/api/clients")
def list_clients():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, bitrix_id, email, city, discount, status FROM clients ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "bitrix_id": r[2], "email": r[3], "city": r[4], "discount": r[5], "status": r[6]} for r in rows]

@app.post("/api/clients")
def create_client(data: ClientCreate):
    try:
        now = datetime.now().isoformat()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(q("""
            INSERT INTO clients (name, bitrix_id, email, city, discount, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """), (data.name, data.bitrix_id, data.email, data.city, data.discount, 'active', now))
        client_id = get_last_id(cursor)
        conn.commit()
        conn.close()
        return {"status": "created", "client_id": client_id}
    except Exception as e:
        logger.error(f"[!] [create_client ERROR] {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Ошибка создания клиента: {e}")

@app.get("/api/clients/{client_id}")
def get_client(client_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT id, name, bitrix_id, email, city, discount, status FROM clients WHERE id = %s"), (client_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Клиент не найден.")
    return {"id": row[0], "name": row[1], "bitrix_id": row[2], "email": row[3], "city": row[4], "discount": row[5], "status": row[6]}

@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM clients WHERE id = %s"), (client_id,))
    conn.commit()
    conn.close()
    logger.info(f"[Client] Удалён клиент #{client_id}")
    return {"status": "deleted", "client_id": client_id}

@app.get("/api/events")
def list_events(from_date: Optional[str] = None, to_date: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("""
        SELECT id, title, description, kind, start, "end", all_day, location, client_id, color, created_at, updated_at
        FROM calendar_events
        WHERE (%s IS NULL OR start >= %s) AND (%s IS NULL OR start <= %s)
        ORDER BY start
    """), (from_date, from_date, to_date, to_date))
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": r[0], "title": r[1], "description": r[2], "kind": r[3],
        "start": r[4], "end": r[5], "all_day": r[6], "location": r[7],
        "client_id": r[8], "color": r[9], "created_at": r[10], "updated_at": r[11],
    } for r in rows]

@app.post("/api/events")
def create_event(data: CalendarEventIn):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(q("""
        INSERT INTO calendar_events (title, description, kind, start, "end", all_day, location, client_id, color, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """), (data.title, data.description, data.kind, data.start.isoformat(),
            data.end.isoformat() if data.end else None, data.all_day,
            data.location, data.client_id, data.color, now, now))
    event_id = get_last_id(cursor)
    conn.commit()
    conn.close()
    return {"id": event_id, **data.dict(), "created_at": now, "updated_at": now}

@app.patch("/api/events/{event_id}")
def update_event(event_id: int, data: CalendarEventIn):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(q("""
        UPDATE calendar_events SET title=%s, description=%s, kind=%s, start=%s, "end"=%s,
        all_day=%s, location=%s, client_id=%s, color=%s, updated_at=%s WHERE id=%s
    """), (data.title, data.description, data.kind, data.start.isoformat(),
            data.end.isoformat() if data.end else None, data.all_day,
            data.location, data.client_id, data.color, now, event_id))
    conn.commit()
    conn.close()
    return {"id": event_id, **data.dict(), "updated_at": now}

@app.delete("/api/events/{event_id}")
def delete_event(event_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM calendar_events WHERE id = %s"), (event_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

import asyncio
import concurrent.futures
import re
import socket

@app.get("/api/search/email")
async def search_email(q: str):
    """Search email by company name across clients and leads."""
    conn = get_db()
    cursor = conn.cursor()
    email = None
    source = None

    # 1. Search existing clients
    if _use_pg:
        cursor.execute("SELECT email, name FROM clients WHERE name ILIKE %s LIMIT 1", ('%' + q + '%',))
    else:
        cursor.execute("SELECT email, name FROM clients WHERE name LIKE ? LIMIT 1", ('%' + q + '%',))
    row = cursor.fetchone()
    if row and row[0]:
        email = row[0]
        source = 'client'

    # 2. Search leads (contacts field may contain email)
    if not email:
        if _use_pg:
            cursor.execute("SELECT contacts, name FROM parsed_leads WHERE name ILIKE %s LIMIT 1", ('%' + q + '%',))
        else:
            cursor.execute("SELECT contacts, name FROM parsed_leads WHERE name LIKE ? LIMIT 1", ('%' + q + '%',))
        row = cursor.fetchone()
        if row and row[0]:
            found = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', row[0])
            if found:
                email = found.group(0)
                source = 'lead'

    conn.close()

    # 3. Web search fallback — run in dedicated thread pool (max 3 workers)
    # so it doesn't starve the default executor used by FastAPI
    if not email:
        try:
            _web_search_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix='websearch')
            loop = asyncio.get_event_loop()
            web_email = await asyncio.wait_for(
                loop.run_in_executor(_web_search_pool, _search_web_email, q),
                timeout=6.0
            )
            if web_email:
                email = web_email
                source = 'web'
        except asyncio.TimeoutError:
            logger.warning(f'[WebSearch] Timeout for query: {q}')
        except Exception as e:
            logger.warning(f'[WebSearch] Error: {e}')

    return {"email": email, "source": source}

def _extract_urls_from_ddg(html: str) -> List[str]:
    """Extract real URLs from DuckDuckGo HTML results."""
    urls = []
    # DuckDuckGo wraps links in redirects: //duckduckgo.com/l/?uddg=URL or uddg= in middle
    for match in re.finditer(r'uddg=([^"\'&\s]+)', html):
        try:
            url = urllib.parse.unquote(match.group(1))
            if url.startswith('http') and 'duckduckgo.com' not in url:
                urls.append(url)
        except Exception:
            pass
    # Fallback: try standard href links
    if not urls:
        for match in re.finditer(r'href=["\'](https?://[^"\'<>\s]+)', html):
            url = match.group(1)
            if 'duckduckgo.com' not in url and 'w3.org' not in url and 'javascript:' not in url:
                urls.append(url)
    # Deduplicate
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:3]

def _extract_urls_from_ddg_lite(html: str) -> List[str]:
    """Extract real URLs from DuckDuckGo Lite HTML results."""
    urls = []
    # DDG Lite uses plain links like <a href="http://example.com" ...>
    # Also has class="result-link" or similar
    for match in re.finditer(r'<a[^>]*href=["\'](https?://[^"\'<>\s]+)["\'][^>]*class=["\'][^"\']*result', html, re.IGNORECASE):
        url = match.group(1)
        if 'duckduckgo.com' not in url and 'w3.org' not in url:
            urls.append(url)
    # Fallback: any http link in result rows
    if not urls:
        for match in re.finditer(r'<td[^>]*>.*?<a[^>]*href=["\'](https?://[^"\'<>\s]+)["\']', html, re.DOTALL):
            url = match.group(1)
            if 'duckduckgo.com' not in url and 'w3.org' not in url and 'javascript:' not in url:
                urls.append(url)
    # Fallback 2: any direct link
    if not urls:
        for match in re.finditer(r'href=["\'](https?://[^"\'<>\s]+)', html):
            url = match.group(1)
            if 'duckduckgo.com' not in url and 'w3.org' not in url and 'javascript:' not in url:
                urls.append(url)
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:3]

def _extract_urls_from_bing(html: str) -> List[str]:
    """Extract real URLs from Bing HTML results."""
    urls = []
    # Bing uses class="b_algo" with h2 > a href
    for match in re.finditer(r'<h2[^>]*>\s*<a[^>]*href=["\'](https?://[^"\'<>\s]+)', html):
        url = match.group(1)
        if 'bing.com' not in url and 'microsoft.com' not in url and 'w3.org' not in url:
            urls.append(url)
    # Fallback all links
    if not urls:
        for match in re.finditer(r'href=["\'](https?://[^"\'<>\s]+)', html):
            url = match.group(1)
            if 'bing.com' not in url and 'microsoft.com' not in url and 'w3.org' not in url and 'javascript:' not in url:
                urls.append(url)
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:3]

def _scrape_emails_from_page(url: str) -> Optional[str]:
    """Fetch a page and extract the first valid email. Fast, 3s timeout."""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(3)
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9',
            }
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8', errors='ignore')
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
            for email in emails:
                email_lower = email.lower()
                if any(x in email_lower for x in ['noreply', 'no-reply', 'support@', 'info@', 'admin@', 'help@', 'marketing@', 'sales@', 'abuse@', 'postmaster@', 'webmaster@', 'example.com', 'test.com', 'domain.com', 'yourcompany.com']):
                    continue
                if email_lower.endswith(('.png', '.jpg', '.gif', '.svg', '.webp', '.css', '.js')):
                    continue
                return email
    except Exception:
        pass
    finally:
        socket.setdefaulttimeout(old_timeout)
    return None

def _search_serpapi_email(query: str) -> Optional[str]:
    """Search via SerpApi Google, scrape top results for email."""
    if not SERPAPI_KEY:
        return None
    term = f'{query} email контакты'
    try:
        params = urllib.parse.urlencode({
            'engine': 'google',
            'q': term,
            'api_key': SERPAPI_KEY,
            'gl': 'ru',
            'hl': 'ru',
            'num': '5',
        })
        req = urllib.request.Request(
            f'https://serpapi.com/search?{params}',
            headers={'Accept': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            organic = data.get('organic_results', [])
            for result in organic[:2]:
                url = result.get('link')
                if url:
                    email = _scrape_emails_from_page(url)
                    if email:
                        logger.info(f'[SerpApi] Найден email для "{query}" на {url}')
                        return email
    except Exception as e:
        logger.warning(f'[SerpApi] Error: {e}')
    return None

def _search_web_email(query: str) -> Optional[str]:
    """Fast web search: SerpApi -> DDG Lite -> Bing. Max ~10s total."""
    term = f'{query} email контакты'

    # 1. SerpApi (Google via API)
    try:
        email = _search_serpapi_email(query)
        if email:
            return email
    except Exception:
        pass

    # 2. DuckDuckGo Lite (simpler HTML, no JS)
    try:
        data = urllib.parse.urlencode({'q': term, 'kl': 'ru-ru'}).encode('utf-8')
        req = urllib.request.Request(
            'https://lite.duckduckgo.com/lite/',
            data=data,
            method='POST',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            html = response.read().decode('utf-8', errors='ignore')
            urls = _extract_urls_from_ddg_lite(html)[:2]
            for url in urls:
                email = _scrape_emails_from_page(url)
                if email:
                    return email
    except Exception:
        pass

    # 2. Bing
    try:
        search_query = urllib.parse.quote(term)
        req = urllib.request.Request(
            f'https://www.bing.com/search?q={search_query}&setmkt=ru-RU',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9',
            }
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            html = response.read().decode('utf-8', errors='ignore')
            urls = _extract_urls_from_bing(html)[:2]
            for url in urls:
                email = _scrape_emails_from_page(url)
                if email:
                    return email
    except Exception:
        pass

    return None

# === PROPOSAL (КП) ENDPOINTS ===

@app.post("/api/proposals")
def create_proposal(data: ProposalInput, current_user: dict = Depends(get_current_user)):
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("""
        INSERT INTO proposals (client_id, created_by, title, total_amount, discount_global, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """), (data.client_id, current_user['id'], data.title or f"КП от {now[:10]}", 0, data.discount_global, 'draft', now, now))
    proposal_id = get_last_id(cursor)
    cursor.execute("SELECT COUNT(*) FROM proposals")
    seq_num = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    logger.info(f"[Proposal] Создано КП #{proposal_id} (seq: {seq_num}) для клиента {data.client_id} user={current_user['id']}")
    return {"status": "created", "proposal_id": proposal_id, "seq_num": seq_num}

@app.get("/api/proposals")
def list_proposals():
    conn = get_db()
    cursor = conn.cursor()
    # Use ROW_NUMBER() to calculate exact sequence number across all records, starting from 1 for the oldest record
    cursor.execute("""
        SELECT p.id, p.client_id, c.name as client_name, p.title, p.total_amount,
               p.discount_global, p.status, p.email_sent, p.created_at,
               ROW_NUMBER() OVER (ORDER BY p.id) as seq_num
        FROM proposals p LEFT JOIN clients c ON p.client_id = c.id
        ORDER BY p.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "client_id": r[1], "client_name": r[2], "title": r[3], "total_amount": float(r[4]) if r[4] else 0,
             "discount_global": r[5], "status": r[6], "email_sent": r[7], "created_at": r[8], "seq_num": r[9]} for r in rows]

@app.get("/api/proposals/{proposal_id}")
def get_proposal(proposal_id: int):
    conn = get_db()
    cursor = conn.cursor()
    # Wrap in subquery to get sequential number for specific proposal
    cursor.execute(q("""
        SELECT sub.id, sub.client_id, sub.client_name, sub.email, sub.title, sub.total_amount, sub.discount_global, sub.status, sub.email_sent, sub.created_at, sub.seq_num
        FROM (
            SELECT p.id, p.client_id, c.name as client_name, c.email, p.title, p.total_amount, p.discount_global, p.status, p.email_sent, p.created_at,
                   ROW_NUMBER() OVER (ORDER BY p.id) as seq_num
            FROM proposals p LEFT JOIN clients c ON p.client_id = c.id
        ) sub
        WHERE sub.id = %s
    """), (proposal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="КП не найдено.")
    proposal = {"id": row[0], "client_id": row[1], "client_name": row[2], "client_email": row[3],
                "title": row[4], "total_amount": float(row[5]) if row[5] else 0, "discount_global": row[6],
                "status": row[7], "email_sent": row[8], "created_at": row[9], "seq_num": row[10]}
    cursor.execute(q("""
        SELECT pi.id, pi.sku_id, s.sku, s.type, s.brand, pi.qty, pi.price_base, pi.discount_item, pi.price_final
        FROM proposal_items pi JOIN sku_catalog s ON pi.sku_id = s.id WHERE pi.proposal_id = %s
    """), (proposal_id,))
    items = []
    for r in cursor.fetchall():
        items.append({"id": r[0], "sku_id": r[1], "sku": r[2], "type": r[3], "brand": r[4],
                      "qty": r[5], "price_base": float(r[6]) if r[6] else 0,
                      "discount_item": r[7], "price_final": float(r[8]) if r[8] else 0})
    proposal["items"] = items
    conn.close()
    return proposal

@app.get("/kp/{proposal_id}", response_class=HTMLResponse)
def render_proposal_public(proposal_id: int):
    """Public proposal page — no auth required."""
    proposal = get_proposal(proposal_id)
    conn = get_db()
    cursor = conn.cursor()

    # Get manager info
    manager = {"name": "", "phone": "", "email": "", "initials": "—"}
    # created_by may not be set on old proposals
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
    total_before = sum(item["price_base"] * item["qty"] for item in proposal["items"])
    discount_amount = total_before - sum(item["price_final"] * item["qty"] for item in proposal["items"])
    total_after = sum(item["price_final"] * item["qty"] for item in proposal["items"])
    vat = total_after * 0.2

    ctx = {
        "kp_id": proposal_id,
        "kp_number": f"#{proposal.get('seq_num', proposal_id)}",
        "date": today.strftime("%d.%m.%Y"),
        "valid_until": valid.strftime("%d.%m.%Y"),
        "title": proposal.get("title", "Коммерческое предложение"),
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
                "price_final": it["price_final"],
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

@app.get("/api/proposals/{proposal_id}/pdf")
async def download_proposal_pdf(proposal_id: int, request: Request):
    """Generate and return a PDF version of the proposal via Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(status_code=501, detail="Playwright не установлен. Установите: pip install playwright && playwright install chromium")

    base_url = str(request.base_url).rstrip("/")
    pdf_path = f"/tmp/kp_{proposal_id}.pdf" if os.name != "nt" else f"C:/Windows/Temp/kp_{proposal_id}.pdf"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{base_url}/kp/{proposal_id}", wait_until="networkidle")
        await page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"}
        )
        await browser.close()

    from fastapi.responses import FileResponse
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"KP_HHB_{proposal_id}.pdf",
        background=None,
    )

@app.post("/api/proposals/{proposal_id}/items")
def add_proposal_item(proposal_id: int, data: ProposalItemInput):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT price FROM sku_catalog WHERE id = %s"), (data.sku_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="SKU не найден.")
    price_base = float(row[0])
    price_final = price_base * (1 - data.discount_item / 100)
    cursor.execute(q("""
        INSERT INTO proposal_items (proposal_id, sku_id, qty, price_base, discount_item, price_final)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """), (proposal_id, data.sku_id, data.qty, price_base, data.discount_item, price_final))
    item_id = get_last_id(cursor)
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    logger.info(f"[Proposal] В КП #{proposal_id} добавлена позиция #{item_id} (SKU {data.sku_id})")
    return {"status": "added", "item_id": item_id}

@app.put("/api/proposals/{proposal_id}/items/{item_id}")
def update_proposal_item(proposal_id: int, item_id: int, data: ProposalItemInput):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT price_base FROM proposal_items WHERE id = %s AND proposal_id = %s"), (item_id, proposal_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Позиция не найдена.")
    price_base = float(row[0])
    price_final = price_base * (1 - data.discount_item / 100)
    cursor.execute(q("""
        UPDATE proposal_items SET qty = %s, discount_item = %s, price_final = %s WHERE id = %s
    """), (data.qty, data.discount_item, price_final, item_id))
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    return {"status": "updated", "item_id": item_id}

@app.delete("/api/proposals/{proposal_id}/items/{item_id}")
def delete_proposal_item(proposal_id: int, item_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM proposal_items WHERE id = %s AND proposal_id = %s"), (item_id, proposal_id))
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    logger.info(f"[Proposal] Из КП #{proposal_id} удалена позиция #{item_id}")
    return {"status": "deleted", "item_id": item_id}

@app.delete("/api/proposals/{proposal_id}")
def delete_proposal(proposal_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM proposal_items WHERE proposal_id = %s"), (proposal_id,))
    cursor.execute(q("DELETE FROM proposals WHERE id = %s"), (proposal_id,))
    conn.commit()
    conn.close()
    logger.info(f"[Proposal] Удалено КП #{proposal_id}")
    return {"status": "deleted", "proposal_id": proposal_id}

@app.delete("/api/proposals")
def delete_all_proposals():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM proposal_items"))
    cursor.execute(q("DELETE FROM proposals"))
    conn.commit()
    conn.close()
    logger.info("[Proposal] Удалены все КП")
    return {"status": "deleted_all"}

@app.post("/api/proposals/{proposal_id}/discount")
def set_proposal_discount(proposal_id: int, data: DiscountInput):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("UPDATE proposals SET discount_global = %s, updated_at = %s WHERE id = %s"),
                   (data.discount_global, datetime.now().isoformat(), proposal_id))
    conn.commit()
    conn.close()
    recalc_proposal_total(proposal_id)
    logger.info(f"[Proposal] Установлена глобальная скидка {data.discount_global}% для КП #{proposal_id}")
    return {"status": "updated", "discount_global": data.discount_global}

@app.post("/api/kp/{proposal_id}/accept")
def accept_proposal(proposal_id: int):
    """Client accepts the proposal via public page button."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("UPDATE proposals SET status = %s, updated_at = %s WHERE id = %s"),
                   ('accepted', datetime.now().isoformat(), proposal_id))
    conn.commit()
    conn.close()
    logger.info(f"[Proposal] КП #{proposal_id} принято клиентом.")
    return {"status": "accepted", "proposal_id": proposal_id}

# === EMAIL SENDING ===

def send_proposal_email(proposal_id: int, to_email: str, subject: str):
    """Send proposal as HTML email via SMTP."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.yandex.ru")
    smtp_port = int(os.getenv("SMTP_PORT", 465))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        logger.warning("[Email] SMTP credentials not configured. Skipping real send.")
        return False

    proposal = get_proposal(proposal_id)
    items_html = ""
    for item in proposal["items"]:
        items_html += f"""
        <tr>
            <td style="border:1px solid #ddd;padding:8px">{item['sku']}</td>
            <td style="border:1px solid #ddd;padding:8px">{item['type']}</td>
            <td style="border:1px solid #ddd;padding:8px;text-align:center">{item['qty']}</td>
            <td style="border:1px solid #ddd;padding:8px;text-align:right">{item['price_base']:,.0f} ₽</td>
            <td style="border:1px solid #ddd;padding:8px;text-align:center">{item['discount_item']}%</td>
            <td style="border:1px solid #ddd;padding:8px;text-align:right">{item['price_final']:,.0f} ₽</td>
            <td style="border:1px solid #ddd;padding:8px;text-align:right">{item['price_final'] * item['qty']:,.0f} ₽</td>
        </tr>
        """

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif">
    <div style="max-width:700px;margin:0 auto">
        <div style="border-bottom:3px solid #C8102E;padding-bottom:15px;margin-bottom:20px">
            <h2 style="color:#1A237E;margin:0">ООО «Компонент Сервис»</h2>
            <p style="color:#666;margin:5px 0 0;font-size:12px">Официальный Дистрибьютор HHB & FKD в России</p>
        </div>
        <h3 style="color:#C8102E">{proposal['title']}</h3>
        <p><strong>Клиент:</strong> {proposal['client_name']}</p>
        <p><strong>Дата:</strong> {proposal['created_at'][:10]}</p>
        <p><strong>Глобальная скидка:</strong> {proposal['discount_global']}%</p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:15px">
            <thead style="background:#1A237E;color:#fff">
                <tr>
                    <th style="padding:8px;border:1px solid #ddd">Артикул</th>
                    <th style="padding:8px;border:1px solid #ddd">Описание</th>
                    <th style="padding:8px;border:1px solid #ddd">Кол-во</th>
                    <th style="padding:8px;border:1px solid #ddd">База</th>
                    <th style="padding:8px;border:1px solid #ddd">Скидка</th>
                    <th style="padding:8px;border:1px solid #ddd">Цена</th>
                    <th style="padding:8px;border:1px solid #ddd">Сумма</th>
                </tr>
            </thead>
            <tbody>{items_html}</tbody>
        </table>
        <p style="text-align:right;font-size:18px;font-weight:bold;margin-top:20px">
            ИТОГО: {proposal['total_amount']:,.0f} ₽
        </p>
        <div style="margin-top:30px;padding-top:15px;border-top:1px solid #ddd;font-size:11px;color:#999">
            По всем вопросам: +7 (473) 255-00-00 | csbrg.ru
        </div>
    </div>
    </body></html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
        logger.info(f"[Email] КП #{proposal_id} отправлено на {to_email}")
        return True
    except Exception as e:
        logger.error(f"[!] [Email Error] Ошибка отправки КП #{proposal_id}: {e}")
        return False

@app.post("/api/proposals/{proposal_id}/send")
def send_proposal(proposal_id: int, data: SendEmailInput):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT c.email, c.name FROM proposals p JOIN clients c ON p.client_id = c.id WHERE p.id = %s"), (proposal_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="КП или клиент не найден.")
    client_email = data.recipient_email or row[0]
    client_name = row[1]
    if not client_email:
        raise HTTPException(status_code=400, detail="У клиента не указан email. Введите вручную.")

    sent = send_proposal_email(proposal_id, client_email, data.subject)
    if sent:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(q("UPDATE proposals SET email_sent = TRUE, status = 'sent', updated_at = %s WHERE id = %s"),
                       (datetime.now().isoformat(), proposal_id))
        conn.commit()
        conn.close()
        # Also queue a task for CRM logging
        if qm is not None:
            qm.add_task("crm_lead", {"type": "proposal_sent", "proposal_id": proposal_id, "client_email": client_email, "client_name": client_name}, max_retries=3)
        else:
            logger.warning(f"[Queue] CRM-задача для КП #{proposal_id} не добавлена: очередь отключена.")
        return {"status": "sent", "proposal_id": proposal_id, "recipient": client_email}
    else:
        raise HTTPException(status_code=500, detail="Не удалось отправить email. Проверьте настройки SMTP.")

# === INTELLECTUAL AI DEEPSEEK ROUTE WITH ADVANCED LOGGING ===

@app.post("/api/ai/search")
def ai_search(payload: AiSearchRequest):
    query = payload.query.strip()
    logger.info(f"[AI Search] Получен новый поисковый запрос: '{query}'")
    
    # Measure response time
    start_time = time.time()
    
    # Determine which API Key to use
    api_key = payload.api_key or os.getenv("DEEPSEEK_API_KEY")
    
    if api_key:
        try:
            logger.info("[AI Search] Отправка запроса к официальному API DeepSeek...")
            
            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты профессиональный консультант ООО Компонент Сервис, эксперт по премиум-подшипникам HHB и FKD. Выдай строго JSON с полями title, desc, price, stock, cross."
                        },
                        {"role": "user", "content": query}
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                }).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}'
                }
            )
            
            with urllib.request.urlopen(req, timeout=12) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                
            elapsed_time = time.time() - start_time
            logger.info(f"[AI Search] Успешный ответ от DeepSeek за {elapsed_time:.2f} сек.")
            
            ai_content = json.loads(resp_data["choices"][0]["message"]["content"])
            return ai_content
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"[!] [AI Search Error] Сбой при запросе к DeepSeek API через {elapsed_time:.2f} сек. Ошибка: {e}")
            logger.error(traceback.format_exc())
            # Graceful fallback to local scenario database
            logger.warning("[AI Search] Активирован локальный резервный офлайн-режим для бесперебойной работы фронтенда.")
    
    # Local fallback scenario database (Instant response)
    logger.info("[AI Search] Использование встроенного офлайн-генератора решений HHB/FKD.")
    time.sleep(1.2) # Realistic synthetic thinking latency
    return get_local_fallback_response(query)

def get_local_fallback_response(query):
    query_lower = query.lower()
    if any(k in query_lower for k in ["6205", "skf", "фаг", "fag"]):
        return {
            "title": "HHB 6205-2RS C3 Premium",
            "desc": "Премиальный шариковый радиальный подшипник HHB (аналог SKF 6205-2RS1). Снабжен двусторонним износостойким уплотнением из каучука для удержания смазки и радиальным зазором C3 для бесперебойной работы при температуре до +120°C.",
            "price": "420 ₽",
            "stock": "1 240 шт",
            "cross": "SKF 6205-2RS1/C3, FAG 6205-2RSR-C3"
        }
    elif any(k in query_lower for k in ["нори", "вал 30", "пыл", "uc"]):
        return {
            "title": "HHB UCP 206 (корпусной узел на лапах)",
            "desc": "Профессиональный подшипниковый узел (чугунный литой корпус UCP206 + радиальный подшипник UC206). Оснащен трехкромочным уплотнением LS3, исключающим попадание мелкодисперсной зерновой пыли нории внутрь узла. Заполнен высококачественной агропылевой смазкой.",
            "price": "1 180 ₽",
            "stock": "86 комплектов",
            "cross": "FKL UCP206, SKF SY 30 TF"
        }
    else:
        return {
            "title": "HHB UCF 208 (фланцевый квадратный узел)",
            "desc": "Высоконадежный фланцевый узел (четырехболтовый квадратный корпус F208 + подшипник UC208). Рассчитан на высокие статические и динамические радиальные нагрузки. Посадочный вал 40 мм. Подходит для приводов элеваторов и тяжелых сеялок.",
            "price": "1 420 ₽",
            "stock": "140 шт",
            "cross": "FKL UCF208, SKF FY 40 TF"
        }

# === KIMI AI CHAT ENDPOINT ===

@app.post("/api/ai/chat")
def ai_chat(payload: AiChatRequest, current_user: dict = Depends(get_current_user)):
    messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    result = run_kimi_agent(messages, current_user)
    return {"message": result}

# === AUTH & EMPLOYEE DASHBOARD ENDPOINTS ===

@app.post("/api/auth/login")
def login(data: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT id, password_hash, name, role FROM users WHERE username = %s"), (data.username,))
    row = cursor.fetchone()
    conn.close()
    if not row or not verify_password(data.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = secrets.token_urlsafe(32)
    active_tokens[token] = row[0]
    return {"token": token, "user": {"id": row[0], "username": data.username, "name": row[2], "role": row[3]}}

@app.post("/api/auth/logout")
def logout(request: Request):
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        token = auth[7:]
        active_tokens.pop(token, None)
    return {"detail": "Logged out"}

@app.get("/api/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.get("/api/users")
def list_users(current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ('admin', 'manager'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT id, username, name, role FROM users ORDER BY name"))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "name": r[2], "role": r[3]} for r in rows]

@app.post("/api/users")
def create_user(data: UserCreate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin required")
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        cursor.execute(q("""
            INSERT INTO users (username, password_hash, name, role, created_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """), (data.username, hash_password(data.password), data.name, data.role, now))
        conn.commit()
        uid = get_last_id(cursor)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=f"Username already exists or invalid data: {e}")
    conn.close()
    return {"id": uid, "username": data.username, "name": data.name, "role": data.role}

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Admin required")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM users WHERE id = %s"), (user_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": user_id}

@app.get("/api/plans")
def list_plans(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if current_user['role'] in ('admin', 'manager'):
        cursor.execute(q("""
            SELECT p.id, p.user_id, u.name, p.month, p.year, p.calls_target, p.registrations_target
            FROM employee_plans p
            JOIN users u ON u.id = p.user_id
            ORDER BY p.year DESC, p.month DESC
        """))
    else:
        cursor.execute(q("""
            SELECT p.id, p.user_id, u.name, p.month, p.year, p.calls_target, p.registrations_target
            FROM employee_plans p
            JOIN users u ON u.id = p.user_id
            WHERE p.user_id = %s
            ORDER BY p.year DESC, p.month DESC
        """), (current_user['id'],))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "user_name": r[2], "month": r[3], "year": r[4], "calls_target": r[5], "registrations_target": r[6]} for r in rows]

@app.post("/api/plans")
def create_plan(data: PlanCreate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ('admin', 'manager'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(q("""
        INSERT INTO employee_plans (user_id, month, year, calls_target, registrations_target, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    """), (data.user_id, data.month, data.year, data.calls_target, data.registrations_target, now, now))
    conn.commit()
    pid = get_last_id(cursor)
    conn.close()
    return {"id": pid, "user_id": data.user_id, "month": data.month, "year": data.year, "calls_target": data.calls_target, "registrations_target": data.registrations_target}

@app.get("/api/calls")
def list_calls(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if current_user['role'] in ('admin', 'manager'):
        cursor.execute(q("""
            SELECT c.id, c.user_id, u.name, c.client_id, c.lead_id, c.client_name, c.from_number, c.to_number, c.direction,
                   c.call_date, c.status, c.duration, c.recording_url, c.notes, c.is_new_registration, c.bitrix_call_id, c.created_at, c.updated_at
            FROM call_logs c
            JOIN users u ON u.id = c.user_id
            ORDER BY c.call_date DESC, c.created_at DESC
        """))
    else:
        cursor.execute(q("""
            SELECT c.id, c.user_id, u.name, c.client_id, c.lead_id, c.client_name, c.from_number, c.to_number, c.direction,
                   c.call_date, c.status, c.duration, c.recording_url, c.notes, c.is_new_registration, c.bitrix_call_id, c.created_at, c.updated_at
            FROM call_logs c
            JOIN users u ON u.id = c.user_id
            WHERE c.user_id = %s
            ORDER BY c.call_date DESC, c.created_at DESC
        """), (current_user['id'],))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "user_name": r[2], "client_id": r[3], "lead_id": r[4], "client_name": r[5], "from_number": r[6], "to_number": r[7], "direction": r[8],
             "call_date": r[9], "status": r[10], "duration": r[11], "recording_url": r[12], "notes": r[13], "is_new_registration": bool(r[14]), "bitrix_call_id": r[15], "created_at": r[16], "updated_at": r[17]} for r in rows]

@app.post("/api/calls")
def create_call(data: CallLogCreate, current_user: dict = Depends(get_current_user)):
    try:
        logger.info(f'[create_call] user={current_user["id"]} data={data.model_dump_json()}')
        conn = get_db()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(q("""
            INSERT INTO call_logs (user_id, client_id, lead_id, client_name, from_number, to_number, direction,
                                   call_date, status, duration, recording_url, notes, is_new_registration, bitrix_call_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """), (current_user['id'], data.client_id, data.lead_id, data.client_name, data.from_number, data.to_number, data.direction,
               data.call_date, data.status, data.duration, data.recording_url, data.notes, int(data.is_new_registration), data.bitrix_call_id, now, now))
        conn.commit()
        cid = get_last_id(cursor)
        conn.close()
        return {"id": cid, "user_id": current_user['id'], "client_name": data.client_name, "call_date": data.call_date, "status": data.status, "notes": data.notes, "is_new_registration": data.is_new_registration}
    except Exception as e:
        logger.error(f"[!] [create_call ERROR] {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Ошибка сохранения звонка: {e}")

@app.put("/api/calls/{call_id}")
def update_call(call_id: int, data: CallLogCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if current_user['role'] not in ('admin', 'manager'):
        cursor.execute(q("SELECT user_id FROM call_logs WHERE id = %s"), (call_id,))
        row = cursor.fetchone()
        if not row or row[0] != current_user['id']:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")
    now = datetime.now().isoformat()
    cursor.execute(q("""
        UPDATE call_logs SET client_id = %s, lead_id = %s, client_name = %s, from_number = %s, to_number = %s,
            direction = %s, call_date = %s, status = %s, duration = %s, recording_url = %s, notes = %s,
            is_new_registration = %s, bitrix_call_id = %s, updated_at = %s
        WHERE id = %s
    """), (data.client_id, data.lead_id, data.client_name, data.from_number, data.to_number, data.direction,
           data.call_date, data.status, data.duration, data.recording_url, data.notes, int(data.is_new_registration), data.bitrix_call_id, now, call_id))
    conn.commit()
    conn.close()
    return {"status": "updated", "id": call_id}

@app.delete("/api/calls/{call_id}")
def delete_call(call_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if current_user['role'] not in ('admin', 'manager'):
        cursor.execute(q("SELECT user_id FROM call_logs WHERE id = %s"), (call_id,))
        row = cursor.fetchone()
        if not row or row[0] != current_user['id']:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")
    cursor.execute(q("DELETE FROM call_logs WHERE id = %s"), (call_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": call_id}

# === LEAD PARSER & DAILY PLAN ENDPOINTS ===

@app.get("/api/leads")
def list_leads(
    query: Optional[str] = None,
    region: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    cursor = conn.cursor()
    sql = q("""
        SELECT l.id, l.name, l.category, l.city, l.contacts, l.need_description,
               l.query, l.region, l.status, l.assigned_to, u.name, l.call_count, l.created_at
        FROM parsed_leads l
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE 1=1
    """)
    params = []
    if current_user['role'] == 'employee':
        sql += q(" AND (l.assigned_to = %s OR l.assigned_to IS NULL)")
        params.append(current_user['id'])
    if query:
        sql += q(" AND l.query = %s")
        params.append(query)
    if region:
        sql += q(" AND l.region = %s")
        params.append(region)
    if status:
        sql += q(" AND l.status = %s")
        params.append(status)
    if assigned_to is not None:
        sql += q(" AND l.assigned_to = %s")
        params.append(assigned_to)
    sql += q(" ORDER BY l.created_at DESC")
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "category": r[2], "city": r[3], "contacts": r[4],
         "need_description": r[5], "query": r[6], "region": r[7], "status": r[8],
         "assigned_to": r[9], "assigned_name": r[10], "call_count": r[11] or 0, "created_at": r[12]}
        for r in rows
    ]

@app.post("/api/leads")
def create_lead(data: dict, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    assigned_to = data.get('assigned_to')
    # Employees can only create leads assigned to themselves
    if current_user['role'] == 'employee':
        if not assigned_to:
            assigned_to = current_user['id']
        elif assigned_to != current_user['id']:
            raise HTTPException(status_code=403, detail="Forbidden")
    cursor.execute(q("""
        INSERT INTO parsed_leads (name, category, city, contacts, need_description, query, region, status, assigned_to, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """), (data.get('name'), data.get('category'), data.get('city'), data.get('contacts'),
           data.get('need_description'), data.get('query'), data.get('region'), data.get('status', 'new'), assigned_to, now, now))
    conn.commit()
    lid = get_last_id(cursor)
    conn.close()
    return {"id": lid, "status": "created"}

@app.put("/api/leads/{lead_id}/assign")
def assign_lead(lead_id: int, data: LeadAssign, current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ('admin', 'manager'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(q("""
        UPDATE parsed_leads SET assigned_to = %s, updated_at = %s
        WHERE id = %s
    """), (data.user_id, now, lead_id))
    conn.commit()
    conn.close()
    return {"status": "assigned", "lead_id": lead_id, "assigned_to": data.user_id}

@app.put("/api/leads/{lead_id}/status")
def update_lead_status(lead_id: int, data: LeadStatusUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if current_user['role'] == 'employee':
        cursor.execute(q("SELECT assigned_to FROM parsed_leads WHERE id = %s"), (lead_id,))
        row = cursor.fetchone()
        if not row or row[0] != current_user['id']:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")
    now = datetime.now().isoformat()
    cursor.execute(q("""
        UPDATE parsed_leads SET status = %s, updated_at = %s
        WHERE id = %s
    """), (data.status, now, lead_id))
    conn.commit()
    conn.close()
    return {"status": "updated", "lead_id": lead_id, "new_status": data.status}

@app.patch("/api/leads/{lead_id}")
def patch_lead(lead_id: int, data: dict, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    if current_user['role'] == 'employee':
        cursor.execute(q("SELECT assigned_to FROM parsed_leads WHERE id = %s"), (lead_id,))
        row = cursor.fetchone()
        if not row or row[0] != current_user['id']:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")
    now = datetime.now().isoformat()
    allowed = {'name', 'category', 'city', 'contacts', 'need_description', 'query', 'region', 'status'}
    fields = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not fields:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update.")
    set_clause = ", ".join([f"{k} = %s" for k in fields.keys()])
    sql = f"UPDATE parsed_leads SET {set_clause}, updated_at = %s WHERE id = %s"
    cursor.execute(q(sql), (*fields.values(), now, lead_id))
    conn.commit()
    conn.close()
    return {"status": "updated", "lead_id": lead_id, "fields": list(fields.keys())}

@app.get("/api/daily-plan")
def get_daily_plan(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now()
    month = now.month
    year = now.year
    today_str = now.strftime('%Y-%m-%d')

    # Получить всех сотрудников или текущего
    if current_user['role'] in ('admin', 'manager'):
        cursor.execute(q("SELECT id, name FROM users WHERE role = 'employee' ORDER BY name"))
        users = cursor.fetchall()
    else:
        users = [(current_user['id'], current_user['name'])]

    result = []
    for uid, uname in users:
        cursor.execute(q("""
            SELECT calls_target, registrations_target FROM employee_plans
            WHERE user_id = %s AND month = %s AND year = %s
        """), (uid, month, year))
        plan_row = cursor.fetchone()
        calls_target = plan_row[0] if plan_row else 0
        regs_target = plan_row[1] if plan_row else 0

        # Рабочие дни примерно 22 в месяц
        work_days = 22
        daily_calls = round(calls_target / work_days) if calls_target else 0

        # Сколько звонков сделано сегодня
        cursor.execute(q("""
            SELECT COUNT(*) FROM call_logs
            WHERE user_id = %s AND call_date = %s AND status = 'completed'
        """), (uid, today_str))
        completed_today = cursor.fetchone()[0]

        # Сколько лидов назначено
        cursor.execute(q("""
            SELECT COUNT(*) FROM parsed_leads WHERE assigned_to = %s AND status != 'converted'
        """), (uid,))
        assigned_leads = cursor.fetchone()[0]

        result.append({
            "user_id": uid,
            "user_name": uname,
            "calls_target": calls_target,
            "registrations_target": regs_target,
            "daily_calls": daily_calls,
            "completed_today": completed_today,
            "assigned_leads": assigned_leads,
            "remaining_calls": max(0, daily_calls - completed_today)
        })

    conn.close()
    return result

@app.post("/api/daily-plan/generate")
def generate_daily_plan(current_user: dict = Depends(get_current_user)):
    if current_user['role'] not in ('admin', 'manager'):
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db()
    cursor = conn.cursor()

    # Получить всех менеджеров
    cursor.execute(q("SELECT id, name FROM users WHERE role = 'employee' ORDER BY name"))
    employees = cursor.fetchall()
    if not employees:
        conn.close()
        return {"detail": "No employees found"}

    # Получить все нераспределенные лиды
    cursor.execute(q("""
        SELECT id FROM parsed_leads WHERE assigned_to IS NULL AND status = 'new' ORDER BY created_at DESC
    """))
    unassigned = [r[0] for r in cursor.fetchall()]

    now = datetime.now().isoformat()
    assigned_count = 0
    for i, lead_id in enumerate(unassigned):
        emp_id = employees[i % len(employees)][0]
        cursor.execute(q("""
            UPDATE parsed_leads SET assigned_to = %s, updated_at = %s WHERE id = %s
        """), (emp_id, now, lead_id))
        assigned_count += 1

    conn.commit()
    conn.close()
    return {"detail": f"Assigned {assigned_count} leads to {len(employees)} employees"}

if __name__ == "__main__":
    logger.info("[Server] Запуск веб-сервера FastAPI на http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
