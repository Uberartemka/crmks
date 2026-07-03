# 🎀 Хэндофф сессии 2026-07-04

> Точка возобновления для следующей сессии. Подхватим с любого пункта из «Что осталось».

## 📍 Проект

**frontcrm** — CRM для индустриальных дистрибьюторов подшипников. Vue 3 + FastAPI + PostgreSQL.

- **Репо:** [github.com/Uberartemka/crmks](https://github.com/Uberartemka/crmks) — `main` HEAD `2bf7077`; **рабочая ветка `feat/import-kyk-products`** HEAD `2869157` (задеплоена, не в main)
- **Локальный путь:** `D:\Projects\frontcrm`
- **Тесты:** 72/72 зелёные (`cd backend && python -m pytest`)

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

### 5. Импорт kyk.products (Plan, выполнен)
- `plans/2026-07-04-import-kyk-products.md` — ✅ **выполнен** (ветка `feat/import-kyk-products`)
- Скрипт-трансформер `backend/scripts/import_kyk_products.py`: staging → products (INSERT + ENRICH через COALESCE), case-insensitive brand/category lookup ('Kyk'→'KYK'), Unix-sec → timestamptz конверсия, 12 тестов
- Delivery `deploy/import_kyk_products.sh`: COPY с JOIN с сайт-сервера → CSV → staging в CRM
- **735 товаров залиты** на прод: 478 → **1213 total** (563 active, 650 hidden). Все 735 с полными характеристиками (rs_min/load/rpm/seal/weight).
- Ветка запушена, на CRM-сервере `feat/import-kyk-products` активна (не смержена в main — см. Known issue #8)
- Тесты: **72/72 зелёные**

### 6. Прочее
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
8. **Ветка `feat/import-kyk-products` не смержена в main.** Код задеплоен на CRM-сервер (там активна эта ветка), но в GitHub-`main` его нет. Перед след. деплоем/работой — смержить через PR или fast-forward.
9. **Code-форматы CRM и kyk НЕ совпадают → enrich не сработал.** CRM хранит sku_catalog-коды как «Подшипник HQ6203ZZC3+ KYK», kyk-источник — как чистый артикул «6203 ZZ». При импорте получили **0 совпадений** → все 735 зашли как INSERT (не обновили характеристики у существующих 357 KYK-записей). Если нужно обогатить старые — отдельная задача с нормализацией маппинга (вытащить голый артикул из строки).
10. **Retail/wholesale цены — отдельная задача.** Сейчас price_new/price_old переносятся 1:1. Модель «розница/опт» требует миграции (price_retail/price_wholesale), логично делать вместе с мультитенантностью (per-tenant цены).
11. **API v1 list vs detail — разные наборы полей.** `GET /api/v1/products` отдаёт лёгкую карточку (без rs_min/load/rpm/seal/weight); `GET /api/v1/products/{id}` — полную. Это намеренно (компактный list).

---

## 📋 Что осталось (в порядке приоритета)

| # | Задача | Сложность |
|---|---|---|
| 1 | **Смержить `feat/import-kyk-products` в main** (код на проде, но ветка не в main) | тривиально |
| 2 | **Нормализация code-маппинга** — обогатить 357 старых KYK-записей sku_catalog характеристиками из kyk (нужна логика извлечения чистого артикула из «Подшипник HQ…+ KYK») | средняя |
| 3 | API-ключи в `.env` (KIMI/CF/SERPAPI) | тривиально |
| 4 | SSL/домен для CRM (`certbot --nginx`) | тривиально |
| 5 | **Plan 2: Мультитенантность** (tenants + RLS + middleware) — фундамент для приёма 2-й компании | высокая |
| 6 | Plan 3: Кастомные поля (jsonb) | средняя |
| 7 | Plan 4: Redis-очередь (ARQ/RQ) — заменит QueueManager | средняя |
| 8 | Plan 5: Процессная модель + pgbouncer + `/health`+`/ready` | средняя |
| 9 | Plan 6: Кэш метаданных | низкая |
| 10 | Retail/wholesale цены (миграция price_retail/price_wholesale) — вместе с мультитенантностью | средняя |
| 11 | Переделка сайтов под `/api/v1` | высокая (трогает живое) |
| 12 | 1С-интеграция (writer остатков через `POST /api/v1/products/{id}/stock`) | высокая |

---

## 🧭 Как войти в курс завтра

Просто скажи:
- **«смерджим ветку»** → PR `feat/import-kyk-products` → main (или fast-forward)
- **«давай обогатим старые KYK»** → задача #2: нормализация code-маппинга
- **«давай мультитенантность»** → запущу `writing-plans` для Plan 2
- **«впишем API-ключи»** → 2 минуты, помогу с командами
- **«хочу SSL»** → certbot + nginx
- или любую другую точку из списка выше

Рабочая ветка `feat/import-kyk-products` задеплоена на прод (1213 товаров, 735 с характеристиками), тесты 72/72 зелёные. Подхватим с любого места за минуту.
