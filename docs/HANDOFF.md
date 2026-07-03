# 🎀 Хэндофф сессии 2026-07-04

> Точка возобновления для следующей сессии. Подхватим с любого пункта из «Что осталось».

## 📍 Проект

**frontcrm** — CRM для индустриальных дистрибьюторов подшипников. Vue 3 + FastAPI + PostgreSQL.

- **Репо:** [github.com/Uberartemka/crmks](https://github.com/Uberartemka/crmks) (ветка `main`, HEAD `2bf7077`)
- **Локальный путь:** `D:\Projects\frontcrm`
- **Тесты:** 60/60 зелёные (`cd backend && python -m pytest`)

## 🌍 Серверы

| Сервер | IP | Что на нём |
|---|---|---|
| **CRM (новый)** | `72.56.246.21` | CRM: FastAPI + watchdog + nginx + Redis + Postgres. `ssh -i ~/.ssh/kyk_server_key root@72.56.246.21` |
| **Сайты** | `193.164.149.3` | 3 сайта: csbrg.ru (главный, мультибренд), hhb, kykbrg.ru. Общая БД `hhb_b2b` (478 SKU) + отдельная БД `kyk` (735 товаров). Доступ тот же ключ. |

**Пароли на CRM-сервере:** `/root/crmks_db_password.txt`, `/root/crmks_redis_password.txt`

---

## ✅ Что сделано за сессию

### 1. Спеки и планы (в `docs/superpowers/`)
- `specs/2026-07-03-multitenancy-and-scalability-design.md` — большая спека: мультитенантность (tenants + RLS), кастомные поля (jsonb), отказоустойчивость (watchdog, Redis-очередь), масштабируемость (5 процессов + pgbouncer). **2 раунда техревью зашиты** (`WITH CHECK`, `SET LOCAL`, `statement_cache_size=0`, JWT-инвалидация).
- `specs/2026-07-04-unified-catalog-api-design.md` — каталог + API v1
- `plans/2026-07-03-watchdog-and-job-queue-migration.md` — ✅ **выполнен**
- `plans/2026-07-04-unified-catalog-api.md` — ✅ **выполнен**

### 2. Watchdog (Plan 1, выполнен)
- Миграция 001: `job_queue` (claimed_at, process_after, timestamptz)
- Watchdog-процесс: реанимация stalled-задач по task_type, cleanup orphan Chromium, exponential backoff с jitter
- Atomic claim (`FOR UPDATE SKIP LOCKED` + `process_after`)
- systemd unit, 23 теста

### 3. Каталог + API v1 (выполнен)
- Миграция 003: `brands` / `categories` (parent_id) / `products` (полные характеристики: rs_min, static_load, dynamic_load, rpm_oil, rpm_grease, seal_type, weight, application[])
- Сервис `catalog_v1_service`: list/get/brands/categories/update_stock
- Роуты `/api/v1/*` (публичное чтение, B2B-токен на запись)
- Скрипт `import_from_sku_catalog` (трансформация + дедупликация)
- Redis-кэш инвалидация
- 37 новых тестов (60 всего)

### 4. Деплой
- `deploy/setup.sh`, `deploy/cloud-init.yml` (с фиксом бага `NC`), `deploy/update.sh`, systemd-юниты, nginx-конфиг
- CRM поднята на 72.56.246.21: api/watchdog/nginx/redis/postgres — все active
- 478 товаров KYK/FKD/HHB залиты в `products`, API v1 отвечает (проверено через публичный IP)

### 5. Прочее
- `kykbrg-site/` вынесен из репо в `D:/Projects/kykbrg-site` + добавлен в `.gitignore`
- Revert `a2c183b` (снятые role-checks) на main — авторизация рабочая

---

## 🚨 Known issues / trade-offs (важно помнить!)

1. **`proposal_items.sku_id` имеет FK на `sku_catalog(id)` ON DELETE CASCADE.** КП ссылаются на старый каталог. Перед удалением `sku_catalog` (после миграции сайтов) нужно перевести КП на `products.id`.
2. **API-ключи в `.env` = REPLACE_ME.** AI-функции (Kimi/CF/SERPAPI) не работают, пока не впишешь. На сервере: `/var/www/crmks/backend/.env` → `systemctl restart crmks-api`.
3. **Нет SSL/домена** — CRM доступна по http://72.56.246.21. Когда купишь домен: `certbot --nginx -d <домен>`.
4. **`/api/v1/products/{id}/stock` (GET) не сделан** — решили, что избыточен (`product_card` уже возвращает stock+price).
5. **Сайты пока ходят в свои БД напрямую** — не в CRM API. Переключение сайтов = отдельная задача.
6. **seed-noise** в `api.log` (duplicate key на sku_catalog при старте) — косметика.
7. **Миграция 002 сделана толерантной** к отсутствию `sku_catalog` (важно для тестов/свежих БД).

---

## 📋 Что осталось (в порядке приоритета)

| # | Задача | Сложность |
|---|---|---|
| 1 | **Импорт `kyk.products` (735)** с сайтов-сервера в CRM `products` — наполнит характеристики (rs_min/load/rpm), которых нет у FKD/HHB | высокая (другая схема, нужна трансформация) |
| 2 | API-ключи в `.env` (KIMI/CF/SERPAPI) | тривиально |
| 3 | SSL/домен для CRM (`certbot --nginx`) | тривиально |
| 4 | **Plan 2: Мультитенантность** (tenants + RLS + middleware) — фундамент для приёма 2-й компании | высокая |
| 5 | Plan 3: Кастомные поля (jsonb) | средняя |
| 6 | Plan 4: Redis-очередь (ARQ/RQ) — заменит QueueManager | средняя |
| 7 | Plan 5: Процессная модель + pgbouncer + `/health`+`/ready` | средняя |
| 8 | Plan 6: Кэш метаданных | низкая |
| 9 | Переделка сайтов под `/api/v1` | высокая (трогает живое) |
| 10 | 1С-интеграция (writer остатков через `POST /api/v1/products/{id}/stock`) | высокая |

---

## 🧭 Как войти в курс завтра

Просто скажи:
- **«продолжим с kyk»** → импорт 735 товаров (я сделаю скрипт-трансформер, как с sku_catalog)
- **«давай мультитенантность»** → запущу `writing-plans` для Plan 2
- **«впишем API-ключи»** → 2 минуты, помогу с командами
- **«хочу SSL»** → certbot + nginx
- или любую другую точку из списка выше

Все коммиты на main, тесты 60/60 зелёные, прод живой. Подхватим с любого места за минуту.
