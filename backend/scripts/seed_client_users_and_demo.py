"""Idempotent seeder for Group C activation: client-role users + demo data.

Creates:
  A. 5 client-role users bound to the 5 seed clients (db_init.py seed),
     matched by stable `bitrix_id` (client names contain guillemets and are
     fragile to match on). Fixed dev/demo passwords.
  B. Demo orders — several with status in (delivered/paid/shipped) and
     spread across the last ~6 months, so /api/reports/metrics shows real
     revenue / avg check / conversion / 6-month dynamics.
  C. Demo machinery + defects per client.

Each block only runs if the target table is empty (COUNT(*) == 0), so the
script is safe to re-run. Fixed passwords are DEV/DEMO ONLY — rotate before
any production use.

Run:
    python -m scripts.seed_client_users_and_demo
or:
    python backend/scripts/seed_client_users_and_demo.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger("HHB_B2B")

# ---- Fixed dev/demo credentials (NOT for production without rotation) ----
# username, display name, client bitrix_id, password
CLIENT_USERS = [
    ("agroeco", "Закупщик АГРОЭКО", "BX_1245", "agroeco2026"),
    ("econiva", "Закупщик ЭКОНИВА", "BX_3312", "econiva2026"),
    ("miratorg", "Закупщик МИРАТОРГ", "BX_8821", "miratorg2026"),
    ("rusagro", "Закупщик РУСАГРО", "BX_9901", "rusagro2026"),
    ("elevator", "Инженер Элеватора", "BX_1122", "elevator2026"),
]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat()


def _client_id_by_bitrix(conn, bitrix_id: str) -> int | None:
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM clients WHERE bitrix_id = %s", (bitrix_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


def _admin_id(conn) -> int | None:
    """Return the id of the first admin user (created_by for demo records)."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


def seed_client_users(conn, hash_password) -> dict:
    """Create client-role users bound to seed clients. Idempotent."""
    from utils.auth_utils import hash_password as _hp  # noqa: F811

    stats = {"created": 0, "skipped": 0, "missing_client": []}
    cur = conn.cursor()

    # Skip entirely if client users already exist.
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'client'")
    if cur.fetchone()[0] > 0:
        logger.info("[seed-users] client users already present — skipping.")
        stats["skipped"] = len(CLIENT_USERS)
        cur.close()
        return stats

    now = _now_iso()
    for username, name, bitrix_id, password in CLIENT_USERS:
        client_id = _client_id_by_bitrix(conn, bitrix_id)
        if not client_id:
            logger.warning(f"[seed-users] no client with bitrix_id={bitrix_id} — skipping {username}")
            stats["missing_client"].append(username)
            continue
        try:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, name, role, client_id, created_at)
                VALUES (%s, %s, %s, 'client', %s, %s)
                """,
                (username, _hp(password), name, client_id, now),
            )
            conn.commit()
            stats["created"] += 1
            logger.info(f"[seed-users] created client user '{username}' -> client_id={client_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"[seed-users] failed to create {username}: {e}")
            stats["skipped"] += 1

    cur.close()
    return stats


def seed_demo_orders(conn) -> dict:
    """Insert demo orders spread across ~6 months. Several 'monetized' statuses
    (delivered/paid/shipped) so /api/reports/metrics shows real numbers."""
    stats = {"created": 0, "skipped": 0}
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM orders")
    if cur.fetchone()[0] > 0:
        logger.info("[seed-orders] orders already present — skipping.")
        cur.close()
        return stats

    admin = _admin_id(conn)
    if admin is None:
        logger.warning("[seed-orders] no admin user — skipping orders.")
        cur.close()
        return stats

    agroeco = _client_id_by_bitrix(conn, "BX_1245")
    econiva = _client_id_by_bitrix(conn, "BX_3312")
    miratorg = _client_id_by_bitrix(conn, "BX_8821")
    elevator = _client_id_by_bitrix(conn, "BX_1122")

    # client_id, order_number, name, qty, total, status, age_days
    orders = [
        (agroeco, "ORD-2026-0412", "Корпусные узлы HHB UCP206 (x40)", 40, 47200, "delivered", 100),
        (agroeco, "ORD-2026-0517", "Радиальные 6205-2RS C3 (x120)", 120, 50400, "paid", 60),
        (econiva, "ORD-2026-0610", "Сферические 22315-E1-T41A (x6)", 6, 47700, "shipped", 35),
        (miratorg, "ORD-2026-0628", "Натяжные узлы UCT207 (x10)", 10, 18500, "delivered", 18),
        (elevator, "ORD-2026-0701", "Манжеты 30х52х10 (x200)", 200, 36000, "new", 6),
        (econiva, "ORD-2026-0703", "Фланцевые UCF208 (x15)", 15, 21300, "paid", 4),
    ]

    now = _now_iso()
    for client_id, number, name, qty, total, status, age in orders:
        if not client_id:
            continue
        created = _days_ago_iso(age)
        try:
            cur.execute(
                """
                INSERT INTO orders
                    (client_id, created_by, order_number, name, qty, total,
                     status, order_date, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (client_id, admin, number, name, qty, total, status, created[:10], created, now),
            )
            conn.commit()
            stats["created"] += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"[seed-orders] failed: {e}")

    cur.close()
    logger.info(f"[seed-orders] created {stats['created']} demo orders.")
    return stats


def seed_demo_machinery(conn) -> dict:
    """Insert demo equipment/bearing map per client."""
    stats = {"created": 0, "skipped": 0}
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM machinery")
    if cur.fetchone()[0] > 0:
        logger.info("[seed-machinery] machinery already present — skipping.")
        cur.close()
        return stats

    admin = _admin_id(conn)
    if admin is None:
        cur.close()
        return stats

    agroeco = _client_id_by_bitrix(conn, "BX_1245")
    econiva = _client_id_by_bitrix(conn, "BX_3312")
    elevator = _client_id_by_bitrix(conn, "BX_1122")

    # client_id, name, node, bearing, brand, install_date, wear, status
    machines = [
        (agroeco, "Нория НЦ-100", "Приводной барабан", "UCP 206", "HHB", "2024-03-10", 55, "operation"),
        (agroeco, "Конвейер ленточный", "Натяжной вал", "UCF 208", "HHB", "2023-11-22", 82, "wear_warning"),
        (econiva, "Зерносушилка", "Вентилятор", "22315-E1", "HHB", "2025-01-15", 30, "operation"),
        (elevator, "Элеватор нории", "Головка", "6205-2RS", "FKD", "2022-06-01", 88, "replacement"),
    ]

    now = _now_iso()
    for client_id, name, node, bearing, brand, install, wear, status in machines:
        if not client_id:
            continue
        try:
            cur.execute(
                """
                INSERT INTO machinery
                    (client_id, created_by, name, node, bearing, brand,
                     install_date, wear, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (client_id, admin, name, node, bearing, brand, install, wear, status, now, now),
            )
            conn.commit()
            stats["created"] += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"[seed-machinery] failed: {e}")

    cur.close()
    logger.info(f"[seed-machinery] created {stats['created']} demo machines.")
    return stats


def seed_demo_defects(conn) -> dict:
    """Insert demo defect records per client."""
    stats = {"created": 0, "skipped": 0}
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM defects")
    if cur.fetchone()[0] > 0:
        logger.info("[seed-defects] defects already present — skipping.")
        cur.close()
        return stats

    admin = _admin_id(conn)
    if admin is None:
        cur.close()
        return stats

    agroeco = _client_id_by_bitrix(conn, "BX_1245")
    miratorg = _client_id_by_bitrix(conn, "BX_8821")
    elevator = _client_id_by_bitrix(conn, "BX_1122")

    # client_id, equipment, bearing, description, status, action, age_days
    defects = [
        (agroeco, "Конвейер ленточный", "UCF 208", "Повышенный люфт, шум при работе.", "in_progress",
         "Заказан ремкомплект, плановая замена через 5 дней.", 8),
        (miratorg, "Нория", "UCP 206", "Течь смазки из корпуса.", "reported",
         "Ждём выезд сервиса для дефектовки.", 3),
        (elevator, "Элеватор", "6205-2RS", "Замена выполнена, новые подшипники установлены.", "resolved",
         "Заменено 4 шт., машина в работе.", 20),
    ]

    now = _now_iso()
    for client_id, equip, bearing, desc, status, action, age in defects:
        if not client_id:
            continue
        detected = _days_ago_iso(age)
        try:
            cur.execute(
                """
                INSERT INTO defects
                    (client_id, created_by, equipment, bearing, description,
                     status, action, detected_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (client_id, admin, equip, bearing, desc, status, action, detected[:10], detected, now),
            )
            conn.commit()
            stats["created"] += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"[seed-defects] failed: {e}")

    cur.close()
    logger.info(f"[seed-defects] created {stats['created']} demo defects.")
    return stats


def run_all(conn) -> dict:
    """Run all seeding blocks."""
    from utils.auth_utils import hash_password

    return {
        "client_users": seed_client_users(conn, hash_password),
        "orders": seed_demo_orders(conn),
        "machinery": seed_demo_machinery(conn),
        "defects": seed_demo_defects(conn),
    }


if __name__ == "__main__":
    import os
    import sys

    import psycopg2
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [seed] %(levelname)s %(message)s")

    # Make `import utils.*` work when run as a plain script (not -m).
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)

    env_path = "/var/www/crmks/backend/.env" if os.path.isdir("/var/www/crmks") else ".env"
    load_dotenv(env_path, override=True)
    dsn = os.environ["DATABASE_URL"]

    conn = psycopg2.connect(dsn)
    try:
        stats = run_all(conn)
        print(stats)
    finally:
        conn.close()
