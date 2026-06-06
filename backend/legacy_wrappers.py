from __future__ import annotations

from startup.db_init import (
    init_catalog_tables as _db_init_catalog_tables,
    migrate_call_logs_columns as _db_migrate_call_logs_columns,
    migrate_proposals_columns as _db_migrate_proposals_columns,
    migrate_tasks_columns as _db_migrate_tasks_columns,
    migrate_notes_columns as _db_migrate_notes_columns,
    seed_data as _db_seed_data,
)


def init_catalog_tables() -> None:
    return _db_init_catalog_tables()


def migrate_call_logs_columns() -> None:
    return _db_migrate_call_logs_columns()


def migrate_proposals_columns() -> None:
    return _db_migrate_proposals_columns()


def migrate_tasks_columns() -> None:
    return _db_migrate_tasks_columns()


def migrate_notes_columns() -> None:
    return _db_migrate_notes_columns()


def seed_data() -> None:
    return _db_seed_data()
