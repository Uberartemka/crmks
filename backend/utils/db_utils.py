from __future__ import annotations

from typing import Any

from db import _use_pg


def get_last_id(cursor: Any) -> Any:
    if _use_pg:
        # PostgreSQL: last INSERT id usually returned via RETURNING or LASTVAL elsewhere,
        # but some legacy code uses cursor.fetchone().
        return cursor.fetchone()[0]
    return cursor.lastrowid


def _ph(count: int) -> str:
    """Return placeholders for current DB driver."""
    if _use_pg:
        return ",".join(["%s"] * count)
    return ",".join(["?"] * count)
