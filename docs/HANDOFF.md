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

### 5b. Proposal-flow переведён на products (Plan, выполнен)
- `plans/2026-07-04-proposals-migrate-to-products.md` — ✅ **выполнен** (ветка `feat/proposals-to-products`)
- **Миграция 004:** `proposal_items.sku_id` FK `sku_catalog(id) CASCADE` → `products(id) RESTRICT`. На пустой `proposal_items` — мгновенно, без data-migration.
- **4 SQL-точки контакта** переведены на `products` (+ JOIN brands): `proposals.py:137` (чтение КП), `proposals.py:346` (цена при создании item), `email_service.py:51` (email-КП), `ai_claude_agent.py:282` (ILIKE-поиск при парсинге).
- **`/api/catalog/skus`** (список SKU для `/admin/proposals`) — переписан на `products + brands + categories`, форма ответа сохранена. **Все 1213 SKU теперь видны в /admin/proposals** (было 478 из sku_catalog).
- Маппинг полей: `sku→code, type→name, brand→brands.name, price→price_new`.
- **Тесты:** 11 новых (миграция 004: 4, proposal-флоу: 4, catalog_skus: 3). Всего **83/83 зелёные**.
- Задеплоено на прод: FK переведён, API рестартован, `6203 ZZ` виден через `/api/catalog/skus` с характеристиками.

### 6. Прочее
- `kykbrg-site/` вынесен из репо в `D:/Projects/kykbrg-site` + добавлен в `.gitignore`
- Revert `a2c183b` (снятые role-checks) на main — авторизация рабочая

---

## 🚨 Known issues / trade-offs (важно помнить!)

1. **✅ РЕШЕНО (морг 004):** `proposal_items.sku_id` теперь FK → `products(id) ON DELETE RESTRICT` (был `sku_catalog CASCADE`). Весь proposal-флоу (proposals, email, AI-парсинг, /api/catalog/skus) читает из `products`. `sku_catalog` больше не используется proposal-флоу, но **таблицу пока НЕ дропаем** (destructive — отдельная задача после подтверждения стабильности).
2. **✅ РЕШЕНО:** AI теперь на **GLM (BigModel, `glm-4.5-flash`)** — ваша подписка GLM вместо Kimi/DeepSeek. Все 3 AI-пути переключены:
   - `call_claude()` каскад (10 точек: парсинг КП, анализ звонков, дневной план, ночной агент...) — GLM primary, Anthropic/Kimi фолбэк
   - `/api/ai/search` — GLM вместо DeepSeek (с markdown-fence strip + timeout 30s)
   - `kimi_client`/agent-loop (`/api/ai/chat`, function calling) — через env: `KIMI_BASE_URL=open.bigmodel.cn`, `KIMI_MODEL=glm-4.5-flash`, CF убран
   - Проверено end-to-end на проде: `/api/ai/search` «роликовый подшипник NU 1008» → реальный GLM-ответ с аналогами.
   - **Ключ в `.env`:** `GLM_API_KEY` (также продублирован как `KIMI_API_KEY` для agent-loop). CF_* vars закомментированы. `SERPAPI_KEY` всё ещё REPLACE_ME (не используется в основном флоу).
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
| 1 | **Смержить `feat/import-kyk-products` + `feat/proposals-to-products` в main** (обе задеплоены на проде, но не в main) | тривиально |
| 2 | **DROP `sku_catalog`** — теперь proposal-флоу не использует её. Сначала убедиться, что ничего другого не сломается (catalog_v1 упоминает). | низкая (после проверки) |
| 3 | **Нормализация code-маппинга** — обогатить 357 старых KYK-записей sku_catalog характеристиками из kyk (нужна логика извлечения чистого артикула из «Подшипник HQ…+ KYK») | средняя |
| 4 | `SERPAPI_KEY` в `.env` (остался REPLACE_ME) — нужен только если используется search-via-SerpAPI; основной AI уже на GLM | тривиально |
| 5 | SSL/домен для CRM (`certbot --nginx`) | тривиально |
| 6 | **Plan 2: Мультитенантность** (tenants + RLS + middleware) — фундамент для приёма 2-й компании | высокая |
| 7 | Plan 3: Кастомные поля (jsonb) | средняя |
| 8 | Plan 4: Redis-очередь (ARQ/RQ) — заменит QueueManager | средняя |
| 9 | Plan 5: Процессная модель + pgbouncer + `/health`+`/ready` | средняя |
| 10 | Plan 6: Кэш метаданных | низкая |
| 11 | Retail/wholesale цены (миграция price_retail/price_wholesale) — вместе с мультитенантностью | средняя |
| 12 | Переделка сайтов под `/api/v1` | высокая (трогает живое) |
| 13 | 1С-интеграция (writer остатков через `POST /api/v1/products/{id}/stock`) | высокая |

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
