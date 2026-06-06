from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore

from scheduler.scheduler_setup import register_scheduler_jobs

logger = logging.getLogger("HHB_B2B")


async def _start_scheduler() -> None:
    scheduler = AsyncIOScheduler()  # type: ignore[operator]

    # Явные job-entrypoints (без fallback на main.py)
    from services.ai_plan_service import run_daily_plans_scheduler
    from services.monitor_service import run_site_monitor_scheduler
    from services.nightly_agent import run_nightly_agent

    register_scheduler_jobs(
        scheduler,
        run_daily_plans_scheduler=run_daily_plans_scheduler,
        run_site_monitor_scheduler=run_site_monitor_scheduler,
        run_nightly_agent=run_nightly_agent,
    )

    scheduler.start()
    logger.info(
        "[Scheduler] Планировщик запущен: daily_plans (8:00), site_monitor (10:00), nightly_review (23:00)"
    )


def register_scheduler_startup(app: FastAPI) -> None:
    # Если APScheduler не установлен — импорт упадёт при старте модуля.
    # В этом проекте APScheduler указан в requirements.txt, поэтому делаем явную связь.
    app.on_event("startup")(_start_scheduler)
