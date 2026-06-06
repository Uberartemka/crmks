"""
Migration script: SQLite -> PostgreSQL
Run AFTER PostgreSQL is installed and running, and the server has been started once
(to create tables in PostgreSQL).
"""

import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = os.getenv("SQLITE_PATH", "D:/pod/backend/catalog.db")
PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")

TABLES = [
    "sku_catalog",
    "clients",
    "proposals",
    "proposal_items",
    "users",
    "employee_plans",
    "call_logs",
    "parsed_leads",
]

COLUMNS = {
    "sku_catalog": ["id", "sku", "category", "gost", "d_inner", "d_outer", "b_width", "type", "brand", "stock", "price", "img", "created_at"],
    "clients": ["id", "name", "bitrix_id", "email", "city", "discount", "status", "created_at"],
    "proposals": ["id", "client_id", "title", "total_amount", "discount_global", "status", "email_sent", "created_at", "updated_at"],
    "proposal_items": ["id", "proposal_id", "sku_id", "qty", "price_base", "discount_item", "price_final"],
    "users": ["id", "username", "password_hash", "name", "role", "created_at"],
    "employee_plans": ["id", "user_id", "month", "year", "calls_target", "registrations_target", "created_at", "updated_at"],
    "call_logs": ["id", "user_id", "client_id", "client_name", "call_date", "status", "notes", "is_new_registration", "created_at"],
    "parsed_leads": ["id", "name", "category", "city", "contacts", "need_description", "query", "region", "status", "assigned_to", "call_count", "created_at", "updated_at"],
}

def migrate():
    print(f"SQLite source: {SQLITE_PATH}")
    print(f"PostgreSQL target: {PG_URL.replace('@', ':***@')}")

    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite file not found at {SQLITE_PATH}")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(PG_URL)
    pg_cursor = pg_conn.cursor()

    total_rows = 0

    for table in TABLES:
        cols = COLUMNS.get(table)
        if not cols:
            print(f"Skipping {table}: no column mapping")
            continue

        # Check if table exists in SQLite
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not sqlite_cursor.fetchone():
            print(f"Skipping {table}: not found in SQLite")
            continue

        # Read from SQLite
        sqlite_cursor.execute(f"SELECT {', '.join(cols)} FROM {table}")
        rows = sqlite_cursor.fetchall()

        if not rows:
            print(f"  {table}: 0 rows (empty)")
            continue

        # Clear PostgreSQL table and reset sequence
        pg_cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")

        # Build INSERT query
        placeholders = ', '.join(['%s'] * len(cols))
        insert_sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES {placeholders}"

        for row in rows:
            pg_cursor.execute(insert_sql, tuple(row))

        # Reset sequence for SERIAL/IDENTITY columns
        pg_cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), coalesce(max(id), 1), max(id) IS NOT NULL) FROM {table}")

        pg_conn.commit()
        print(f"  {table}: {len(rows)} rows migrated")
        total_rows += len(rows)

    pg_cursor.close()
    pg_conn.close()
    sqlite_conn.close()

    print(f"\nDone! Total rows migrated: {total_rows}")
    print("You can now delete catalog.db if you want (keep a backup just in case).")

if __name__ == "__main__":
    confirm = input("This will TRUNCATE PostgreSQL tables and copy data from SQLite. Continue? (yes/no): ")
    if confirm.lower() != "yes":
        print("Cancelled.")
        sys.exit(0)
    migrate()
