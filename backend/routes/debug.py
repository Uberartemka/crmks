"""Temporary debug endpoint to check environment variables."""
import os
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/debug-env")
def debug_env():
    return {
        "DATABASE_URL_exists": "DATABASE_URL" in os.environ,
        "DATABASE_URL_prefix": os.environ.get("DATABASE_URL", "NOT_SET")[:30] if os.environ.get("DATABASE_URL") else "NOT_SET",
        "REDIS_FAIL_FAST": os.environ.get("REDIS_FAIL_FAST", "NOT_SET"),
        "RESTORE_SECRET_exists": "RESTORE_SECRET" in os.environ,
        "PG_URL_used": os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")[:50],
    }
