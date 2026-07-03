import psycopg2
import json
import time
import threading
import logging
import os
from datetime import datetime

# === PostgreSQL-Backed Robust Multithreaded Task Queue Manager ===
# This manager provides a highly resilient, transactional FIFO queue
# stored in PostgreSQL. Ideal for concurrent enterprise-grade B2B integrations (1C, Bitrix24).

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/hhb_b2b")
logger = logging.getLogger("HHB_B2B")


class QueueManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.init_db()
        self.worker_thread = None
        self.running = False

    def init_db(self):
        with self.lock:
            try:
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                # Create job_queue table using PostgreSQL dialect
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS job_queue (
                        id SERIAL PRIMARY KEY,
                        task_type VARCHAR(100) NOT NULL,
                        status VARCHAR(50) NOT NULL DEFAULT 'pending',
                        payload TEXT NOT NULL,
                        retries INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        error_message TEXT,
                        created_at VARCHAR(100) NOT NULL,
                        updated_at VARCHAR(100) NOT NULL
                    )
                    """
                )
                conn.commit()
                conn.close()
                logger.info("[Database] Подключение к PostgreSQL и инициализация таблиц успешны.")
            except Exception as e:
                logger.error(f"[!] [Database Error] Ошибка подключения к PostgreSQL: {e}")
                logger.error(
                    "Пожалуйста, убедитесь, что сервер PostgreSQL запущен и строка подключения в DATABASE_URL верна."
                )

    def add_task(self, task_type, payload, max_retries=3):
        now = datetime.now().isoformat()
        payload_json = json.dumps(payload)

        with self.lock:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            # In PostgreSQL we use %s and RETURNING id to get the inserted serial ID
            cursor.execute(
                """
                INSERT INTO job_queue (task_type, status, payload, max_retries, created_at, updated_at)
                VALUES (%s, 'pending', %s, %s, %s, %s)
                RETURNING id
                """,
                (task_type, payload_json, max_retries, now, now),
            )
            task_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()

        logger.info(f"[Queue] Добавлена задача #{task_id} [{task_type}] в очередь.")
        return task_id

    def get_task_status(self, task_id):
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, task_type, status, retries, max_retries, error_message, updated_at 
            FROM job_queue WHERE id = %s
            """,
            (task_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "id": row[0],
                "type": row[1],
                "status": row[2],
                "retries": row[3],
                "max_retries": row[4],
                "error": row[5],
                "updated_at": row[6],
            }
        return None

    def list_tasks(self, limit=50):
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, task_type, status, retries, max_retries, error_message, created_at 
            FROM job_queue ORDER BY id DESC LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        tasks = []
        for r in rows:
            tasks.append(
                {
                    "id": r[0],
                    "type": r[1],
                    "status": r[2],
                    "retries": r[3],
                    "max_retries": r[4],
                    "error": r[5],
                    "created_at": r[6],
                }
            )
        return tasks

    def get_queue_stats(self):
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM job_queue GROUP BY status")
        rows = cursor.fetchall()
        conn.close()

        stats = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        for r in rows:
            stats[r[0]] = r[1]
        return stats

    def retry_task(self, task_id):
        now = datetime.now().isoformat()
        with self.lock:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_queue 
                SET status = 'pending', retries = 0, error_message = NULL, updated_at = %s
                WHERE id = %s AND status = 'failed'
                """,
                (now, task_id),
            )
            conn.commit()
            conn.close()
        logger.info(f"[Queue] Задача #{task_id} перезапущена вручную.")
        return True

    # === BACKGROUND WORKER THREAD LOGIC ===
    def start_worker(self):
        if not self.running:
            # Check if Chromium is available; warn if not but don't crash the worker
            try:
                from services.pdf_service import ensure_pdf_browser_started, is_chromium_available

                if is_chromium_available():
                    ensure_pdf_browser_started()
                else:
                    logger.warning("[Queue Worker] Chromium/Playwright не установлен — PDF generation будет недоступен. Установите: playwright install chromium")
            except Exception as e:
                logger.warning(f"[Queue Worker] Не удалось заранее стартовать pdf_service Chromium: {e}")

            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("[Queue Worker] Фоновый обработчик очереди запущен успешно.")

    def stop_worker(self):
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()
            logger.info("[Queue Worker] Обработчик очереди остановлен.")

    def _worker_loop(self):
        while self.running:
            try:
                task = self._claim_next_task()
                if task:
                    self._process_task(task)
                else:
                    time.sleep(2)  # Sleep 2 seconds if no pending tasks
            except Exception as e:
                logger.error(f"[!] [Queue Worker Error] Сбой в цикле воркера: {e}")
                time.sleep(5)  # Sleep 5 seconds on database error before retrying

    def _claim_next_task(self):
        """Atomically claim the next eligible pending task.

        Uses FOR UPDATE SKIP LOCKED so multiple workers (or a worker + tests)
        cannot grab the same row. Respects process_after: a task whose
        process_after is in the future (deferred for backoff) is skipped.
        No python-level lock — Postgres row locking is the source of truth.
        """
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE job_queue
                   SET status = 'processing',
                       claimed_at = now(),
                       updated_at = now(),
                       retries = retries + 1
                 WHERE id = (
                   SELECT id FROM job_queue
                    WHERE status = 'pending'
                      AND process_after <= now()
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                 )
                 RETURNING id, task_type, payload, retries, max_retries
                """
            )
            row = cursor.fetchone()
            conn.commit()
            if row:
                task_id, task_type, payload, retries, max_retries = row
                return {
                    "id": task_id,
                    "type": task_type,
                    "payload": json.loads(payload),
                    "retries": retries,
                    "max_retries": max_retries,
                }
            return None
        finally:
            conn.close()

    def _process_task(self, task):
        task_id = task["id"]
        task_type = task["type"]
        payload = task["payload"]
        logger.info(f"[Queue Worker] Обработка задачи #{task_id} [{task_type}]...")

        success = False
        error_msg = None

        try:
            # === CORE TASKS ===
            if task_type == "1c_sync":
                # Simulated heavy 1C inventory import
                logger.info(
                    f"[1С Sync] Синхронизация остатков и цен для артикула: {payload.get('sku')}..."
                )
                time.sleep(3)  # Simulate network/database load
                success = True

            elif task_type == "crm_lead":
                # Simulated Bitrix24 REST API lead submission
                logger.info(f"[Bitrix24] Отправка нового B2B лида '{payload.get('client_name')}' в CRM...")
                time.sleep(2)  # Simulate API request latency
                # Simulate a realistic temporary API error once to show Retry logic!
                if task["retries"] == 0 and payload.get("client_name") == 'ООО "АГРОЭКО"':
                    raise Exception("Bitrix24 API 502 Bad Gateway (Временный сбой сети)")
                success = True

            elif task_type == "email_invoice":
                # Simulated automatic invoice generation and SMTP send
                logger.info(f"[Email] Отправка PDF счета на почту {payload.get('email')}...")
                time.sleep(1.5)
                success = True

            elif task_type == "generate_pdf":
                from services.pdf_service import generate_pdf_and_store

                proposal_id = int(payload["proposal_id"])
                base_url = str(payload["base_url"])
                generate_pdf_and_store(base_url=base_url, proposal_id=proposal_id)
                success = True

            else:
                raise Exception(f"Неизвестный тип задачи: {task_type}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[!] Ошибка при обработке задачи #{task_id}: {error_msg}")

        now = datetime.now().isoformat()
        with self.lock:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()

            if success:
                cursor.execute(
                    "UPDATE job_queue SET status = 'completed', updated_at = %s WHERE id = %s",
                    (now, task_id),
                )
                logger.info(f"[Queue Worker] Задача #{task_id} выполнена успешно!")
            else:
                new_retries = task["retries"] + 1
                if new_retries >= task["max_retries"]:
                    cursor.execute(
                        """
                        UPDATE job_queue 
                        SET status = 'failed', retries = %s, error_message = %s, updated_at = %s 
                        WHERE id = %s
                        """,
                        (new_retries, error_msg, now, task_id),
                    )
                    logger.error(f"[!] [Queue Worker] Задача #{task_id} исчерпала попытки. Статус: FAILED")
                else:
                    cursor.execute(
                        """
                        UPDATE job_queue 
                        SET status = 'pending', retries = %s, error_message = %s, updated_at = %s 
                        WHERE id = %s
                        """,
                        (new_retries, error_msg, now, task_id),
                    )
                    logger.warning(
                        f"[*] [Queue Worker] Задача #{task_id} возвращена в очередь на повтор. "
                        f"Попытка {new_retries}/{task['max_retries']}"
                    )

            conn.commit()
            conn.close()
