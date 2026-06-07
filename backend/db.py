"""
Общий слой работы с БД: подключение + контекст-менеджер курсора.

Импортируется и из main.py, и из ai_tools_*.py.
Не импортирует main.py — никакой цикличности.
"""
import os
import sys
import logging
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv

# Загружаем .env с принудительной перезаписью системных переменных
load_dotenv(override=True)

try:
    import psycopg2
    _HAS_PG = True
except ImportError:
    psycopg2 = None
    _HAS_PG = False

logger = logging.getLogger("HHB_B2B")

PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")

# Default SQLite path — different for Windows vs Linux (Railway)
_DEFAULT_SQLITE = "D:/pod/backend/catalog.db" if os.name == "nt" else "/tmp/catalog.db"
SQLITE_PATH = os.getenv("SQLITE_PATH", _DEFAULT_SQLITE)


def _test_pg(connect_timeout: int = 2) -> bool:
    """Test PostgreSQL connectivity. On Railway the env var is always set."""
    if not _HAS_PG:
        return False
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=connect_timeout)
        conn.close()
        return True
    except Exception:
        return False


# If DATABASE_URL is explicitly set (e.g. Railway Postgres plugin), force PG mode.
# The connection will be retried later in startup_init_db with a longer timeout.
_use_pg = os.getenv("DATABASE_URL") is not None

if _use_pg:
    logger.info(f"[Database] DATABASE_URL найден, режим PostgreSQL. Проверяю соединение...")
    if not _test_pg(connect_timeout=5):
        logger.warning("[Database] PostgreSQL пока не отвечает, но DATABASE_URL задан — продолжаем в PG-режиме.")
else:
    logger.warning("[Database] DATABASE_URL не задан. Fallback на SQLite.")


def get_db():
    if _use_pg:
        return psycopg2.connect(PG_URL)
    return sqlite3.connect(SQLITE_PATH)


def q(sql: str) -> str:
    """Адаптирует SQL под активный диалект."""
    if _use_pg:
        return sql
    return (sql
            .replace("%s", "?")
            .replace("ILIKE", "LIKE")
            .replace("RETURNING id", ""))


@contextmanager
def db_cursor():
    conn = get_db()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
