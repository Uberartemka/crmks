"""
Общий слой работы с БД: подключение + контекст-менеджер курсора.

Импортируется и из main.py, и из ai_tools_*.py.
Не импортирует main.py — никакой цикличности.
"""
import os
import logging
import sqlite3
from contextlib import contextmanager

try:
    import psycopg2
    _HAS_PG = True
except ImportError:
    psycopg2 = None
    _HAS_PG = False

logger = logging.getLogger("HHB_B2B")

PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")
SQLITE_PATH = os.getenv("SQLITE_PATH", "D:/pod/backend/catalog.db")


def _test_pg() -> bool:
    if not _HAS_PG:
        return False
    try:
        conn = psycopg2.connect(PG_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


_use_pg = _test_pg()
if not _use_pg:
    logger.warning("[Database] PostgreSQL недоступен. Fallback на SQLite.")


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
