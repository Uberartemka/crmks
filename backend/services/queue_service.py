from __future__ import annotations

import logging
from fastapi import HTTPException

from db import _use_pg
from queue_manager import QueueManager

logger = logging.getLogger("HHB_B2B")

_qm: QueueManager | None = None


def init_queue_manager() -> None:
    """
    Инициализирует (и стартует) QueueManager.
    Делаем это при старте мейн-модуля, чтобы поведение соответствовало текущему.
    """
    global _qm

    if _use_pg:
        if _qm is None:
            logger.info("[Queue] Инициализация менеджера очередей задач...")
            _qm = QueueManager()
            _qm.start_worker()
    else:
        logger.warning("[Queue] PostgreSQL недоступен — очередь задач отключена для локального SQLite-режима.")
        _qm = None


def get_queue_manager() -> QueueManager:
    if _qm is None:
        raise HTTPException(
            status_code=503,
            detail="Очередь задач недоступна: PostgreSQL не запущен. КП, каталог и клиенты работают в локальном SQLite-режиме.",
        )
    return _qm
