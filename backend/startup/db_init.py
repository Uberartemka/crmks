from __future__ import annotations
import logging

import hashlib
import secrets
from datetime import datetime
from typing import Any, Optional

from db import get_db, q, _use_pg

logger = logging.getLogger("HHB_B2B")


def _ph(count: int) -> str:
    """Return placeholders for current DB driver."""
    if _use_pg:
        return ",".join(["%s"] * count)
    return ",".join(["?"] * count)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    phash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    ).hex()
    return f"{salt}${phash}"


def get_last_id(cursor: Any) -> Any:
    if _use_pg:
        return cursor.fetchone()[0]
    return cursor.lastrowid


def init_catalog_tables() -> None:
    """Initialize SKU catalog, clients, proposals and proposal_items tables."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        if _use_pg:
            # ===== Tables without FK dependencies first =====
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sku_catalog (
                    id SERIAL PRIMARY KEY,
                    sku VARCHAR(200) NOT NULL UNIQUE,
                    category VARCHAR(100), gost VARCHAR(50),
                    d_inner NUMERIC(10,2), d_outer NUMERIC(10,2), b_width NUMERIC(10,2),
                    type VARCHAR(300), brand VARCHAR(50), stock VARCHAR(100),
                    price NUMERIC(12,2) NOT NULL DEFAULT 0,
                    img VARCHAR(300), created_at VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(300) NOT NULL, bitrix_id VARCHAR(100),
                    email VARCHAR(300), city VARCHAR(100),
                    discount INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'active', created_at VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(256) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    role VARCHAR(50) NOT NULL DEFAULT 'employee',
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    created_at VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parsed_leads (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(300) NOT NULL,
                    category VARCHAR(200),
                    city VARCHAR(100),
                    contacts TEXT,
                    need_description TEXT,
                    query VARCHAR(200),
                    region VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'новый',
                    source VARCHAR(100) DEFAULT 'manual',
                    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    call_count INTEGER DEFAULT 0,
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100)
                )
                """
            )
            # ===== Tables that reference users, clients, parsed_leads =====
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    title VARCHAR(300), total_amount NUMERIC(14,2) DEFAULT 0,
                    discount_global INTEGER DEFAULT 0, status VARCHAR(50) DEFAULT 'draft',
                    email_sent BOOLEAN DEFAULT FALSE,
                    created_at VARCHAR(100), updated_at VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS proposal_items (
                    id SERIAL PRIMARY KEY,
                    proposal_id INTEGER REFERENCES proposals(id) ON DELETE CASCADE,
                    sku_id INTEGER REFERENCES sku_catalog(id) ON DELETE CASCADE,
                    qty INTEGER NOT NULL DEFAULT 1,
                    price_base NUMERIC(12,2) NOT NULL DEFAULT 0,
                    discount_item INTEGER DEFAULT 0,
                    price_final NUMERIC(12,2) NOT NULL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
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
                """
            )
            cursor.execute(
                """
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
                """
            )
            cursor.execute(
                """
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
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    assigned_to INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    created_by VARCHAR(100) DEFAULT 'ai_agent',
                    lead_id INTEGER REFERENCES parsed_leads(id) ON DELETE SET NULL,
                    call_id INTEGER REFERENCES call_logs(id) ON DELETE SET NULL,
                    title VARCHAR(300) NOT NULL,
                    description TEXT,
                    priority VARCHAR(50) DEFAULT 'normal',
                    due_date VARCHAR(100),
                    estimated_minutes INTEGER,
                    status VARCHAR(50) DEFAULT 'todo',
                    source VARCHAR(100) DEFAULT 'manual',
                    created_at VARCHAR(100),
                    completed_at VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_plans (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    date DATE NOT NULL,
                    plan_data TEXT NOT NULL,
                    updated_at VARCHAR(100),
                    UNIQUE(user_id, date)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(300),
                    content TEXT NOT NULL,
                    color VARCHAR(20) DEFAULT 'yellow',
                    pinned INTEGER DEFAULT 0,
                    tags TEXT,
                    client_id INTEGER,
                    created_at VARCHAR(100),
                    updated_at VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS defects (
                    id          SERIAL PRIMARY KEY,
                    client_id   INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    equipment   VARCHAR(300) NOT NULL,
                    bearing     VARCHAR(300),
                    description TEXT,
                    status      VARCHAR(50) DEFAULT 'new',
                    action      TEXT,
                    detected_at VARCHAR(100),
                    created_at  VARCHAR(100),
                    updated_at  VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_defects_client ON defects (client_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_defects_status ON defects (status)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS machinery (
                    id          SERIAL PRIMARY KEY,
                    client_id   INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    name        VARCHAR(300) NOT NULL,
                    node        VARCHAR(300),
                    bearing     VARCHAR(300),
                    brand       VARCHAR(100),
                    install_date VARCHAR(100),
                    wear        INTEGER DEFAULT 0,
                    status      VARCHAR(50) DEFAULT 'normal',
                    created_at  VARCHAR(100),
                    updated_at  VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_machinery_client ON machinery (client_id)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id            SERIAL PRIMARY KEY,
                    client_id     INTEGER REFERENCES clients(id) ON DELETE CASCADE,
                    created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    order_number  VARCHAR(100),
                    name          VARCHAR(500) NOT NULL,
                    qty           INTEGER DEFAULT 1,
                    total         NUMERIC(14,2) DEFAULT 0,
                    status        VARCHAR(50) DEFAULT 'new',
                    order_date    VARCHAR(100),
                    created_at    VARCHAR(100),
                    updated_at    VARCHAR(100)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_client ON orders (client_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)
                """
            )
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sku_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT NOT NULL UNIQUE,
                    category TEXT, gost TEXT,
                    d_inner REAL, d_outer REAL, b_width REAL,
                    type TEXT, brand TEXT, stock TEXT,
                    price REAL NOT NULL DEFAULT 0,
                    img TEXT, created_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, bitrix_id TEXT,
                    email TEXT, city TEXT,
                    discount INTEGER NOT NULL DEFAULT 0,
                    status TEXT DEFAULT 'active', created_at TEXT
                )
                """
            )
            cursor.execute(
                """
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
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER,
                    created_by INTEGER,
                    title TEXT, total_amount REAL DEFAULT 0,
                    discount_global INTEGER DEFAULT 0, status TEXT DEFAULT 'draft',
                    email_sent INTEGER DEFAULT 0,
                    created_at TEXT, updated_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS proposal_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER,
                    sku_id INTEGER,
                    qty INTEGER NOT NULL DEFAULT 1,
                    price_base REAL NOT NULL DEFAULT 0,
                    discount_item INTEGER DEFAULT 0,
                    price_final REAL NOT NULL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'employee',
                    client_id INTEGER,
                    created_at TEXT
                )
                """
            )
            cursor.execute(
                """
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
                """
            )
            cursor.execute(
                """
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
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parsed_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT,
                    city TEXT,
                    contacts TEXT,
                    need_description TEXT,
                    query TEXT,
                    region TEXT,
                    status TEXT DEFAULT 'новый',
                    source TEXT DEFAULT 'manual',
                    assigned_to INTEGER,
                    call_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assigned_to INTEGER,
                    created_by TEXT DEFAULT 'ai_agent',
                    lead_id INTEGER,
                    call_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    priority TEXT DEFAULT 'normal',
                    due_date TEXT,
                    estimated_minutes INTEGER,
                    status TEXT DEFAULT 'todo',
                    source TEXT DEFAULT 'manual',
                    created_at TEXT,
                    completed_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    plan_data TEXT NOT NULL,
                    updated_at TEXT,
                    UNIQUE(user_id, date)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT,
                    content TEXT NOT NULL,
                    color TEXT DEFAULT 'yellow',
                    pinned INTEGER DEFAULT 0,
                    tags TEXT,
                    client_id INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS defects (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id   INTEGER,
                    created_by  INTEGER,
                    equipment   TEXT NOT NULL,
                    bearing     TEXT,
                    description TEXT,
                    status      TEXT DEFAULT 'new',
                    action      TEXT,
                    detected_at TEXT,
                    created_at  TEXT,
                    updated_at  TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_defects_client ON defects (client_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_defects_status ON defects (status)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS machinery (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id   INTEGER,
                    created_by  INTEGER,
                    name        TEXT NOT NULL,
                    node        TEXT,
                    bearing     TEXT,
                    brand       TEXT,
                    install_date TEXT,
                    wear        INTEGER DEFAULT 0,
                    status      TEXT DEFAULT 'normal',
                    created_at  TEXT,
                    updated_at  TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_machinery_client ON machinery (client_id)
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id     INTEGER,
                    created_by    INTEGER,
                    order_number  TEXT,
                    name          TEXT NOT NULL,
                    qty           INTEGER DEFAULT 1,
                    total         REAL DEFAULT 0,
                    status        TEXT DEFAULT 'new',
                    order_date    TEXT,
                    created_at    TEXT,
                    updated_at    TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_client ON orders (client_id)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)
                """
            )

        conn.commit()
        logger.info("[Database] Таблицы КП, каталога, клиентов, задач и заметок инициализированы.")
        conn.close()
    except Exception as e:
        logger.error(f"[!] [Database Error] Ошибка инициализации каталога/КП: {e}")


def migrate_call_logs_columns() -> None:
    """Add missing columns to existing call_logs table."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        new_cols = [
            ("lead_id", "INTEGER"),
            ("from_number", "TEXT" if not _use_pg else "VARCHAR(50)"),
            ("to_number", "TEXT" if not _use_pg else "VARCHAR(50)"),
            ("direction", "TEXT" if not _use_pg else "VARCHAR(20)"),
            ("duration", "INTEGER"),
            ("recording_url", "TEXT"),
            ("bitrix_call_id", "TEXT" if not _use_pg else "VARCHAR(100)"),
            ("updated_at", "TEXT" if not _use_pg else "VARCHAR(100)"),
            ("transcript", "TEXT"),
            ("ai_score", "INTEGER"),
            ("ai_analysis", "TEXT"),
        ]
        for col, col_type in new_cols:
            try:
                if _use_pg:
                    cursor.execute(f"ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS {col} {col_type}")
                else:
                    cursor.execute(f"ALTER TABLE call_logs ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        conn.commit()
        conn.close()
        logger.info("[Database] Миграция call_logs выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция call_logs: {e}")


def migrate_proposals_columns() -> None:
    """Add missing columns to existing proposals table."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        if _use_pg:
            cursor.execute("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS created_by INTEGER")
            cursor.execute("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS accepted_at VARCHAR(100)")
        else:
            try:
                cursor.execute("ALTER TABLE proposals ADD COLUMN created_by INTEGER")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE proposals ADD COLUMN accepted_at TEXT")
            except Exception:
                pass

        conn.commit()
        conn.close()
        logger.info("[Database] Миграция proposals выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция proposals: {e}")


def migrate_calendar_events_columns() -> None:
    """Add missing columns to existing calendar_events table."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        if _use_pg:
            cursor.execute("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS user_id INTEGER")
            cursor.execute("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS created_by INTEGER")
        else:
            try:
                cursor.execute("ALTER TABLE calendar_events ADD COLUMN user_id INTEGER")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE calendar_events ADD COLUMN created_by INTEGER")
            except Exception:
                pass

        conn.commit()
        conn.close()
        logger.info("[Database] Миграция calendar_events выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция calendar_events: {e}")


def migrate_tasks_columns() -> None:
    """Add missing columns to existing tasks table."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        new_cols = [
            ("updated_at", "VARCHAR(100)" if _use_pg else "TEXT"),
            ("estimated_minutes", "INTEGER" if _use_pg else "INTEGER"),
        ]
        for col, col_type in new_cols:
            try:
                if _use_pg:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN IF NOT EXISTS {col} {col_type}")
                else:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        conn.commit()
        conn.close()
        logger.info("[Database] Миграция tasks выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция tasks: {e}")


def migrate_notes_columns() -> None:
    """Add missing columns to existing notes table."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        new_cols = [
            ("pinned", "INTEGER DEFAULT 0"),
            ("tags", "TEXT"),
            ("client_id", "INTEGER"),
        ]
        for col, col_type in new_cols:
            try:
                if _use_pg:
                    cursor.execute(f"ALTER TABLE notes ADD COLUMN IF NOT EXISTS {col} {col_type}")
                else:
                    cursor.execute(f"ALTER TABLE notes ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        conn.commit()
        conn.close()
        logger.info("[Database] Миграция notes выполнена.")
    except Exception as e:
        logger.warning(f"[Database] Миграция notes: {e}")


def seed_data() -> None:
    """Seed data: one-time load if tables empty."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sku_catalog")
        if cursor.fetchone()[0] == 0:
            skus = [
                ("HHB UCP 206", "housing", "480206", 30, 62, 38.1, "Корпусной узел на лапах (Pillow Block)", "HHB", "Достаточно", 1180, "images/ucp.jpg"),
                ("HHB UCF 208", "housing", "480208", 40, 80, 49.2, "Квадратный фланцевый узел (Flange Block)", "HHB", "Достаточно", 1420, "images/ucf.jpg"),
                ("HHB UCFL 205", "housing", "480205", 25, 52, 34.1, "Ромбический фланцевый узел (2-bolt Flange)", "HHB", "Достаточно", 980, "images/ucfl.jpg"),
                ("HHB UCT 207", "housing", "480207", 35, 72, 42.9, "Натяжной узел для нории (Take-up Unit)", "HHB", "В наличии", 1850, "images/uct.jpg"),
                ("HHB STAINLESS UC 204", "stainless", "SS480204", 20, 47, 31, "Нержавеющая сталь (Stainless Series)", "HHB", "18 шт", 2950, "images/stainless.jpg"),
                ("FKD UK 208 + H2308", "housing", "UK208", 35, 80, 49, "С конической закрепительной втулкой", "FKD", "95 шт", 1620, "images/uk.jpg"),
                ("FKD NA 206", "housing", "NA206", 30, 62, 36.4, "С эксцентриковым стопорным кольцом", "FKD", "Достаточно", 730, "images/na.jpg"),
                ("HHB 22315-E1-T41A", "roller", "3615", 75, 160, 55, "Сферический роликовый для виброгрохотов", "HHB", "12 шт", 7950, "images/spherical.jpg"),
                ("HHB 6205-2RS C3", "ball", "180205", 25, 52, 15, "Радиальный шариковый с увеличенным зазором", "HHB", "1 240 шт", 420, "frames_eevee/mobile_webp/0060.webp"),
                ("HHB 6206-2RS C3", "ball", "180206", 30, 62, 16, "Радиальный шариковый с зазором C3", "HHB", "850 шт", 540, "frames_eevee/mobile_webp/0060.webp"),
                ("FKD UC 210", "housing", "480210", 50, 90, 51.6, "Шариковый радиальный под закрепительный винт", "FKD", "320 шт", 690, "images/ucp.jpg"),
                ("Сальник 30х52х10 (Манжета)", "cuffs", "8752-79", 30, 52, 10, "Армированная одновальная манжета ГОСТ", "FKD", "Достаточно", 180, "frames_eevee/mobile_webp/0060.webp"),
                ("HHB NU 312 ECP", "roller", "12312", 60, 130, 31, "Цилиндрический роликовый", "HHB", "45 шт", 4300, "images/roller.jpg"),
                ("HHB 6308-2RS", "ball", "180308", 40, 90, 23, "Радиальный шариковый однорядный", "HHB", "560 шт", 890, "images/ball.jpg"),
                ("FKD UCP 209", "housing", "480209", 45, 85, 49.2, "Корпусной узел на лапах", "FKD", "120 шт", 1050, "images/ucp.jpg"),
            ]
            now = datetime.now().isoformat()
            skus = [sku + (now,) for sku in skus]
            cursor.executemany(
                f"""
                INSERT INTO sku_catalog (sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img, created_at)
                VALUES ({_ph(12)})
                """,
                skus,
            )
            logger.info(f"[Seed] Загружено {len(skus)} SKU в каталог.")

        cursor.execute("SELECT COUNT(*) FROM clients")
        if cursor.fetchone()[0] == 0:
            clients = [
                ('ООО "АГРОЭКО"', "BX_1245", "snab@agroeco.ru", "Воронеж", 15, "active"),
                ('ООО "ЭКОНИВА-ЧЕРНОЗЕМЬЕ"', "BX_3312", "zakup@econiva.ru", "Воронеж", 10, "active"),
                ('АПХ "МИРАТОРГ"', "BX_8821", "supply@miratorg.ru", "Орёл", 5, "active"),
                ('ГК "РУСАГРО"', "BX_9901", "tender@rusagro.ru", "Москва", 0, "new"),
                ('ООО "Воронежский Элеватор"', "BX_1122", "main@vorelev.ru", "Воронеж", 20, "vip"),
            ]
            now = datetime.now().isoformat()
            clients = [client + (now,) for client in clients]
            cursor.executemany(
                f"""
                INSERT INTO clients (name, bitrix_id, email, city, discount, status, created_at)
                VALUES ({_ph(7)})
                """,
                clients,
            )
            logger.info(f"[Seed] Загружено {len(clients)} клиентов.")

        # --- Users: создаём единственного admin СО СЛУЧАЙНЫМ паролем при первом
        # запуске (пустая таблица). Никаких demo-кредов, никакого автосброса —
        # пароль меняется только через UI. Пароль выводится в лог ОДИН РАЗ.
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            random_password = secrets.token_urlsafe(12)
            now = datetime.now().isoformat()
            cursor.execute(
                f"""
                INSERT INTO users (username, password_hash, name, role, created_at)
                VALUES ({_ph(5)})
                """,
                ("admin", hash_password(random_password), "Администратор", "admin", now),
            )
            conn.commit()
            logger.warning("=" * 60)
            logger.warning("СОЗДАН ADMIN СО СЛУЧАЙНЫМ ПАРОЛЕМ — сохраните и смените в UI!")
            logger.warning("  Логин: admin")
            logger.warning(f"  Пароль: {random_password}")
            logger.warning("=" * 60)
        # Если users не пуст — НЕ трогаем (никакого автосброса пароля admin).

        cursor.execute("SELECT COUNT(*) FROM parsed_leads")
        if cursor.fetchone()[0] == 0:
            now = datetime.now().isoformat()
            leads = [
                ("Воронежский Мукомольный Комбинат", "Элеватор, Хранение", "Воронеж", "+7 (473) 255-44-12 · vormuk.ru",
                 "Корпусные узлы UCP208 для приводных барабанов норий. Высокая агропыль.", "элеватор", "Воронеж", now, now),
                ("АГРОЭКО-Восток (Элеваторный Хаб)", "Элеватор, Зернохранилище", "Воронеж", "+7 (473) 200-11-11 · agroeco.ru",
                 "Самоустанавливающиеся подшипники серии UC, натяжные узлы UCF206.", "элеватор", "Воронеж", now, now),
                ("Калачеевский Элеватор", "Элеватор, Сушилки", "Калач", "+7 (47363) 2-14-55 · kalachel.ru",
                 "Двухрядные сферические подшипники для вентиляторов зерносушилок.", "элеватор", "Калач", now, now),
                ("Липецкхлебмакаронпром", "Элеватор, Мельница", "Липецк", "+7 (4742) 28-04-12 · lhm.ru",
                 "Премиум подшипники HHB 6205, зазор C3, радиальные.", "элеватор", "Липецк", now, now),
                ("Грибановский Сахарный Завод", "Сахарный завод, Пищевка", "Грибановка", "+7 (47348) 3-01-22",
                 "Подшипники конвейерной ленты сырого жома, нержавеющие корпуса HHB-SS.", "сахарный завод", "Воронеж", now, now),
                ("Павловск Неруд (Карьероуправление)", "Добыча щебня, Карьер", "Павловск", "+7 (47362) 2-15-51 · pavlovskgranit.ru",
                 "Вибростойкие подшипники HHB T41A (22316) для инерционных грохотов. Ударная нагрузка.", "карьер", "Воронеж", now, now),
            ]
            cursor.executemany(
                f"""
                INSERT INTO parsed_leads (name, category, city, contacts, need_description, query, region, created_at, updated_at)
                VALUES ({_ph(9)})
                """,
                leads,
            )
            logger.info(f"[Seed] Загружено {len(leads)} лидов парсера.")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[!] [Seed Error] Ошибка загрузки seed-данных: {e}")


def startup_init_db() -> None:
    """
    One-stop init sequence that used to live in backend/main.py:
    - create tables
    - migrations
    - seed
    """
    init_catalog_tables()
    migrate_call_logs_columns()
    migrate_proposals_columns()
    migrate_calendar_events_columns()
    migrate_tasks_columns()
    migrate_notes_columns()
    seed_data()
