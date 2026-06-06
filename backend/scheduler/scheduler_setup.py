from __future__ import annotations

from typing import Awaitable, Callable, Any


def register_scheduler_jobs(
    scheduler: Any,
    *,
    run_daily_plans_scheduler: Callable[..., Awaitable[Any]],
    run_site_monitor_scheduler: Callable[..., Awaitable[Any]],
    run_nightly_agent: Callable[..., Awaitable[Any]],
) -> None:
    """
    Регистрирует cron-джобы в APScheduler.
    Функции-джобы остаются в main.py, мы только выносим "склейку" в отдельный модуль.
    """
    # План на день — 8:00 для всех менеджеров
    scheduler.add_job(
        run_daily_plans_scheduler,
        "cron",
        hour=8,
        minute=0,
        id="daily_plans",
    )

    # Мониторинг сайтов клиентов — 10:00
    scheduler.add_job(
        run_site_monitor_scheduler,
        "cron",
        hour=10,
        minute=0,
        id="site_monitor",
    )

    # Ночной обход лидов — 23:00
    scheduler.add_job(
        run_nightly_agent,
        "cron",
        hour=23,
        minute=0,
        id="nightly_review",
    )
