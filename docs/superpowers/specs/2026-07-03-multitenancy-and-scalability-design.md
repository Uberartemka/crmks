# CRM: Мультитенантность, кастомизация, отказоустойчивость и масштабируемость

**Дата:** 2026-07-03
**Статус:** Draft (на ревью у пользователя)
**Автор совместной сессии:** пользователь + ассистент

## Контекст и проблема

`frontcrm` — CRM для индустриальных дистрибьюторов и производителей компонентов
(подшипники, крепёж, метизы, электроника...). Сейчас это один тенант: KYK
Подшипники. К концу года планируется выход на **10–20 компаний, 100–200
пользователей**.

Текущая схема PostgreSQL (`hhb_b2b`) **не содержит понятия тенанта** —
`users`, `clients`, `sku_catalog` живут в общем пространстве, без `tenant_id`
или `company_id`. Принять вторую компанию в такую схему = гарантированная
утечка данных между клиентами.

Цель этой спеки — заложить архитектурный фундамент, который:

1. Строго изолирует данные компаний друг от друга.
2. Позволяет настраивать поля под каждую сферу бизнеса без миграций на каждое
   изменение (настройка — услуга, выполняется инженером, не self-serve).
3. Делает фоновые задачи (PDF, 1С, email, AI-агент) устойчивыми к падениям
   процессов и зависаниям.
4. Масштабируется горизонтально от 1 до 20+ компаний без переписывания.

**Главные приоритеты пользователя (явно зафиксированы в сессии):**
масштабируемость и отказоустойчивость. Производительность языка — не
приоритет (язык остаётся Python/FastAPI).

### Что в дизайн НЕ входит (явный YAGNI)

- Переписывание на C / другой язык.
- Своя БД или своя схема на каждый тенант.
- Формулы и вычисляемые кастомные поля.
- Полноценные кастомные сущности (новые таблицы через UI).
- Версионирование схем кастомных полей.
- Celery / RabbitMQ / Kafka.
- Read-реплики Postgres, шардинг, multi-region.
- OpenTelemetry / distributed tracing.
- Self-serve конструктор полей для менеджеров.

---

## Архитектура: два слоя данных

```
                    ┌─────────────────────────────────────┐
   Общие данные     │  БД "catalog"  (SKU)                │  ← общий справочник,
   (не тенантные)   │  читают многие тенанты              │     сейчас это БД kyk
                    └─────────────────────────────────────┘
                                  ▲
                                  │ чтение по доступу
                                  │
   ┌──────────────────────────────┴──────────────────────────────┐
   │   БД "crm"  (одна) — shared schema + tenant_id + RLS         │
   │                                                              │
   │   tenant=1 (подшипники)   tenant=2 (... )   tenant=3 ...     │
   │   clients, leads, calls, proposals, tasks, notes             │
   │   + jsonb-колонка custom для кастомных полей                 │
   └──────────────────────────────────────────────────────────────┘
```

Каталог SKU живёт в отдельной БД (как сейчас `kyk`). CRM-данные (клиенты,
лиды, КП, звонки) — в одной общей БД с изоляцией через `tenant_id` и
Row-Level Security. Архитектура **обратима**: если одна компания вырастет в
монстра, её можно вынести в отдельную БД, не ломая остальных.

---

## Секция 1. Мультитенантность

### Стержневой объект `tenants`

```sql
CREATE TABLE tenants (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,              -- «KYK Подшипники»
    slug        text UNIQUE NOT NULL,       -- 'kyk', 'avangard' — для логов/субдоменов
    industry    text,                       -- 'bearings', 'fasteners', ...
    is_active   boolean DEFAULT true,
    created_at  timestamptz DEFAULT now()
);

INSERT INTO tenants (id, name, slug, industry)
VALUES (1, 'KYK Подшипники', 'kyk', 'bearings');
```

Текущая компания-основатель переносится как `tenant_id = 1`.

### `tenant_id` в каждой операционной таблице

В `clients`, `parsed_leads`, `call_logs`, `proposals`, `proposal_items`,
`tasks`, `notes`, `users`, `employee_plans` добавляется:

```sql
ALTER TABLE clients ADD COLUMN tenant_id bigint NOT NULL DEFAULT 1 REFERENCES tenants(id);
CREATE INDEX ON clients (tenant_id);
```

`DEFAULT 1` — миграционный трюк: существующие строки автоматически уходят в
текущую компанию без ручной перенумерации. **После бэкфилла DEFAULT обязан
быть снят** — иначе новый клиент, для которого забыл проставить `tenant_id`,
тихо приписывается к KYK. Это отдельный пункт в чек-листе миграции:

> **Чек-лист миграции `tenant_id`:**
> 1. `ALTER TABLE ... ADD COLUMN tenant_id bigint NOT NULL DEFAULT 1 REFERENCES tenants(id)`
> 2. `UPDATE ... SET tenant_id = <id новой компании>` для случаев, когда данные
>    уже принадлежат другой компании (на старте — не требуется).
> 3. `CREATE INDEX ... ON <table> (tenant_id)` на каждой операционной таблице.
> 4. **`ALTER TABLE ... ALTER COLUMN tenant_id DROP DEFAULT`** — снять после
>    бэкфилла, чтобы NOT NULL без DEFAULT ловил баг на уровне схемы.
> 5. `ENABLE ROW LEVEL SECURITY` + `CREATE POLICY ... USING ... WITH CHECK`.

### Изоляция в глубину — два слоя

| Слой | Что делает | От чего защищает |
|---|---|---|
| **RLS (Row-Level Security)** в Postgres | Политики на уровне БД: сессия физически не может прочитать/записать строку чужого тенанта | Баг в коде, SQL-инъекция, ошибка в сервисном слое |
| **Tenant middleware** в FastAPI | Достаёт `tenant_id` из JWT, кладёт в `request.state.tenant_id`, выполняет `SET LOCAL app.tenant_id = $1` в БД-сессии | Забытый `WHERE tenant_id = ...` в роуте |

#### RLS-политики: чтение И запись

```sql
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON clients
    USING      (tenant_id = current_setting('app.tenant_id')::bigint)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::bigint);
```

`USING` фильтрует уже существующие строки (защита чтения). `WITH CHECK`
валидирует то, что **записывается** — INSERT/UPDATE с чужим `tenant_id`
(например, баг, оставивший `DEFAULT 1` или NULL) будет отклонён на уровне БД.
Без `WITH CHECK` RLS защищает только чтение, а запись чужого `tenant_id` —
именно тот баг, который страшнее всего.

#### `SET LOCAL` требует явной транзакции

`SET LOCAL app.tenant_id` работает **только внутри транзакции** — вне `BEGIN`
это либо ошибка, либо no-op после первого автокоммита. Поэтому middleware
**обязан** открывать явную транзакцию на каждый запрос и закрывать её в конце
(а не полагаться, что отдельные хендлеры сами как-то управляют транзакциями).
В asyncpg это `async with pool.acquire() as conn: async with conn.transaction(): ...`
в per-request Depends-обёртке.

#### Сервисные/кросс-тенантные пути — fail-closed

`current_setting('app.tenant_id')` без флага `missing_ok` кидает ошибку, если
переменная не установлена. Это **плюс** (fail-closed): забытый путь = явный
падёж, а не тихая утечка. Но для сознательно кросс-тенантных путей
(watchdog, catalog-sync, миграции, superadmin) используем
`current_setting('app.tenant_id', true)` → возвращает `NULL`, который
обрабатывается отдельно (отдельная роль `app_service` с `BYPASSRLS`, либо
явные admin-политики).

### Пользователь в нескольких компаниях

Сейчас — `user ∈ одна компания`. Поддержка мультичленства (таблица
`user_tenants`) добавляется позже, когда появится реальная потребность.

---

## Секция 2. Кастомные поля

Природа кастомизации зафиксирована как **«разные поля у общих сущностей»**.
Подшипникам нужны артикул/производитель, недвижимости — площадь/адрес.
Общие сущности (`client`, `lead`, `proposal`) одинаковые, отличаются наборы
полей.

### Модель: метаописание + jsonb

**Каталог определений** (одна таблица на всю систему):

```sql
CREATE TABLE custom_field_definitions (
    id            bigserial PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    entity        text NOT NULL,         -- 'client', 'lead', 'proposal'
    field_key     text NOT NULL,         -- 'artikul', 'square_m'
    label         text NOT NULL,         -- «Артикул», «Площадь, м²»
    field_type    text NOT NULL,         -- text|number|select|multiselect|date|bool
    options       jsonb,                 -- для select: ["Купля","Продажа"]
    is_required   boolean DEFAULT false,
    is_filterable boolean DEFAULT false, -- нужно ли по нему фильтровать в списках
    sort_order    int DEFAULT 0,
    UNIQUE (tenant_id, entity, field_key)
);
```

**Значения** — в `jsonb`-колонке прямо в сущности:

```sql
ALTER TABLE clients ADD COLUMN custom jsonb DEFAULT '{}'::jsonb;
CREATE INDEX clients_custom_gin ON clients USING gin (custom);
-- clients.custom = {
--   "artikul": "6204-2RS",          -- text → строка
--   "brand": "SKF",                 -- select → строка из options
--   "square_m": 54.5,               -- number → число
--   "tags": ["vip","wholesale"],    -- multiselect → массив строк из options
--   "deal_date": "2026-08-01"       -- date → ISO-строка YYYY-MM-DD
-- }
```

Скалярные типы (`text`, `number`, `select`, `date`, `bool`) хранятся как
примитивы JSON. `multiselect` — всегда как массив строк, даже из одного
элемента, чтобы фильтр `custom @> '{"tags":["vip"]}'` работал единообразно.

Почему jsonb, а не EAV: чтение карточки — один запрос; фильтрация — через
операторы `@>`, `?` с GIN-индексом; добавление поля — без миграций.

### Фильтрация по кастомным полям (требуется явно)

Двухуровневая индексация:

| Тип фильтра | Как индексируем | Пример |
|---|---|---|
| Равенство / принадлежность (select, text, bool) | GIN на всю jsonb-колонку | `custom @> '{"brand":"SKF"}'` |
| Диапазон / сортировка (number, date) | Expression-индекс, создаётся при включении `is_filterable` | `CREATE INDEX ... ON clients (((custom->>'square_m')::numeric))` |

Когда инженер в админке ставит `is_filterable = true`, бэк автоматически
выполняет DDL создания индекса (безопасно, `IF NOT EXISTS`, идемпотентно).
Настройка полей — инженерная задача, не self-serve, поэтому DDL из UI
допустим.

### Валидация на бэке

При каждой записи значений они проверяются против определений:

- тип (`number` → `isinstance(v, (int, float))`);
- обязательность (`is_required` → значение не None);
- опции (`select` → значение входит в `options`).

Без валидации кастомные поля быстро превратятся в мусорку из неконсистентных
значений.

> **Known trade-off:** валидация живёт только в приложении. Любой прямой
> SQL-доступ (миграционный скрипт, ручной фикс в БД, дамп/восстановление)
> её обходит. Для текущего масштаба (настройка = инженерная задача, не
> self-serve) это приемлемо. Если позже появится прямой SQL-доступ шире, чем
> сервисные роли — рассмотреть JSON-schema CHECK-констрейнты или триггеры
> валидации на уровне БД.

### Граница «колонка vs custom»

Поле нужно всем компаниям → обычная колонка (общая аналитика, общие фильтры).
Поле нужно одной сфере → `custom`. `name`, `email`, `status`, `created_at`
остаются колонками.

---

## Секция 3. Отказоустойчивость

### Принцип А — вынести стейт из процесса

| Сейчас | Стало |
|---|---|
| `QueueManager` в фоновом потоке + `job_queue` в PG (в продакшене закомментирован) | Redis-очередь (ARQ/RQ), отдельный worker-процесс |
| APScheduler in-process | Redis JobStore + distributed lock, либо отдельный cron-процесс |

Redis уже стоит и прописан в `REDIS_URL`. Для масштаба проекта (сотни
юзеров, десятки задач в минуту) ARQ (async + Redis) или RQ — ровно. Celery —
оверкилл.

### Принцип Б — health и readiness раздельно

```
GET /health   — процесс жив (всегда 200, если приложение запущено)
GET /ready    — готов принимать трафик (проверяет PG + Redis, 503 если нет)
```

Балансер бьёт в `/ready`. При падении БД воркер уходит из ротации, а не
возвращает 500. Graceful shutdown: при `SIGTERM` перестать принимать новые
задачи, дождаться текущих с таймаутом, закрыть пулы.

### Принцип В — идемпотентность и backoff

Внешние вызовы (Kimi/OpenAI, 1С, Bitrix, SMTP) — через ретраи с
экспоненциальным backoff + jitter и идемпотентным ключом. Для КП-писем ключ =
`proposal_id + version`, чтобы при повторе не уйти два письма.

### Watchdog (приоритет №1 пользователя)

**Миграция `job_queue`:**

```sql
ALTER TABLE job_queue
    ADD COLUMN claimed_at    timestamptz,
    ADD COLUMN process_after timestamptz DEFAULT now(),
    ADD COLUMN attempt       int NOT NULL DEFAULT 0,
    ALTER  COLUMN created_at TYPE timestamptz USING created_at::timestamptz,
    ALTER  COLUMN updated_at TYPE timestamptz USING updated_at::timestamptz;

CREATE INDEX idx_job_queue_claim
    ON job_queue (status, process_after) WHERE status IN ('pending', 'processing');
```

**Атомарный клейм** (без `threading.Lock`, `SKIP LOCKED` разруливает
конкурентность):

```sql
UPDATE job_queue
   SET status = 'processing',
       claimed_at = now(),
       updated_at = now(),
       attempt = attempt + 1
 WHERE id = (
   SELECT id FROM job_queue
    WHERE status = 'pending'
      AND process_after <= now()
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
 )
 RETURNING id, task_type, payload, attempt, max_retries;
```

**Параметры watchdog:**

| Параметр | Значение |
|---|---|
| Частота сканирования | 60 сек |
| `email_invoice`, `crm_lead` | stall timeout = 60 сек |
| `1c_sync` | stall timeout = 10 мин |
| `generate_pdf` | stall timeout = 10 мин + cleanup orphan Chromium |
| Backoff при retry | `2^attempt × (1+random())`, кап на `LEAST(attempt, 6)` |
| Процесс | отдельный `python -m watchdog` под systemd |
| Архивация | (опц., позже) старше 30 дней → `job_queue_archive` |

Таймауты по типу хранятся в коде как dict (`TASK_TIMEOUTS`), а не в БД — это
конфиг, одинаковый для всех тенантов.

**Реанимация зависших** (раз в минуту):

```sql
UPDATE job_queue
   SET status = 'pending',
       claimed_at = NULL,
       updated_at = now(),
       error_message = COALESCE(error_message, '') || E'\n[watchdog] requeued after stall'
 WHERE status = 'processing'
   AND claimed_at < now() - ($1 || ' seconds')::interval;
```

**Backoff-задержка** при ошибке:

```sql
UPDATE job_queue
   SET process_after = now() + make_interval(
         secs => POWER(2, LEAST(attempt, 6)) * (1 + random())
   )
 WHERE id = $1;
```

---

## Секция 4. Масштабируемость

### Процессная модель (target state на своём сервере)

```
                         ┌──────────────┐
                         │   nginx      │  ← TLS, раздаёт фронт (dist/),
                         │  (reverse)   │     проксирует /api → web
                         └──────┬───────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
       ┌──────────┐      ┌──────────┐      ┌──────────┐
       │  web:1   │      │  web:2   │      │  web:N   │  ← uvicorn, горизонтально
       │ (FastAPI)│      │ (FastAPI)│      │ (FastAPI)│
       └────┬─────┘      └────┬─────┘      └────┬─────┘
            └────────────┬────┴─────────────────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
       ┌─────────┐  ┌─────────┐  ┌──────────┐
       │  PG     │  │ Redis   │  │ catalog  │   ← 3 хранилища
       │  (crm)  │  │ (queue/ │  │   DB     │
       │         │  │  cache) │  │  (sku)   │
       └─────────┘  └─────────┘  └──────────┘
                         ▲
            ┌────────────┴────────────┐
            ▼                         ▼
       ┌──────────┐             ┌───────────┐
       │ worker   │             │ watchdog  │   ← отдельные процессы
       │ (ARQ/RQ) │             │ (60s)     │
       └──────────┘             └───────────┘

       ┌──────────────┐
       │ scheduler    │  ← один экземпляр на весь кластер
       │ (cron)       │     (distributed lock в Redis)
       └──────────────┘
```

5 процессов + 3 хранилища, всё под systemd. Каждый процесс делает одну вещь,
падает и рестартит независимо, скейлится отдельно. Больше RPS на API —
добавляется `web:N`. PDF легли под нагрузкой — добавляется `worker:N`.

`web:N` — сколько угодно. `worker:N` — сколько угодно: они читают одну общую
Redis-очередь, конкурентность разруливается на стороне очереди. `scheduler`
и `watchdog` — строго по одному: иначе «план на день» отработает N раз в
8:00, а watchdog повторно реанимирует задачи. Для них — distributed lock в
Redis (атомарный `SET ... NX EX`) или один systemd-unit без реплик.

### Пул соединений — pgbouncer

`pgbouncer` перед Postgres мультиплексирует соединения. Каждый `web:N`
держит пул ~10–20 коннекшнов → 5 воркеров = 50–100 коннекшнов → Postgres
задыхается. PgBouncer оставляет к Postgres ~10 постоянных, от него к
приложению — сколько угодно.

**Гэтча: pgbouncer transaction-pooling + asyncpg prepared statements.**
asyncpg по умолчанию кэширует prepared statements на соединение. В режиме
transaction pooling клиентское «соединение» физически прыгает между разными
серверными коннектами → под нагрузкой в рандомный момент ловим
`prepared statement does not exist`. Решение — отключить кэш на стороне
asyncpg:

```python
crm_pool = await asyncpg.create_pool(
    dsn=CRM_DSN,
    statement_cache_size=0,                  # не кэшировать prepared statements
    server_settings={'statement_cache_size': '0'},  # и на сервере тоже
)
```

Это надо внести в конфигурацию пула сразу, не «когда всплывёт», иначе оно
найдётся продакшен-инцидентом, а не пунктом спеки.

### Подключение к catalog-БД

Второй asyncpg-пул в lifespan, только на чтение:

```python
crm_pool     = await asyncpg.create_pool(dsn=CRM_DSN, ...)
catalog_pool = await asyncpg.create_pool(dsn=CATALOG_DSN, max_size=5)
```

Каталог **не тенантный**, изоляция не через `tenant_id`, а через «какие SKU
этому тенанту разрешены» (таблица `tenant_catalog_access` — отложено, до
появления второй компании-недистрибьютора).

### Кэширование (только метаданные)

| Что кэшировать | TTL | Зачем |
|---|---|---|
| `custom_field_definitions` по `tenant_id` | 5 мин + invalidate по событию | Читается при каждом отображении карточки, меняется редко |
| Каталог SKU (поиск по артикулу) | 1 час + invalidate при 1С-синхронизации | Тяжёлые запросы, меняются раз в день |
| `token_store` (сессии) | TTL токена | Уже Redis, ничего не делаем |
| `tenants` (id → name/slug) | 1 час | Маленькая таблица, читается при каждом запросе |

Принцип кэша: **инвалидация по событию, не по времени.** TTL — страховка.
Изменение field_def → `DEL crm:fielddefs:{tenant_id}`. 1С-синхронизация →
`DEL catalog:*`.

**Не кэшируем** операционные данные (`clients`, `leads`, `proposals`):
stale-кэш = рассинхрон, нужна свежесть.

---

## Рекомендуемый порядок реализации

(Детальный план — отдельный документ через `writing-plans`.)

1. **Watchdog + миграция `job_queue`** — приоритет №1 пользователя, быстро и
   сразу поднимает надёжность фоновых задач.
2. **Мультитенантность** — фундамент, без которого нельзя принимать вторую
   компанию. Обязательные подзадачи (иначе всплывут багами после деплоя):
   - 2a. Таблица `tenants`, добавление `tenant_id` по операционным таблицам
     с `DEFAULT 1`, бэкфилл, **снятие DEFAULT** (см. чек-лист выше).
   - 2b. **`CREATE POLICY ... USING ... WITH CHECK`** на каждой таблице —
     защита и чтения, и записи.
   - 2c. **Tenant middleware с явной транзакцией** + `SET LOCAL app.tenant_id`
     внутри неё (`SET LOCAL` вне `BEGIN` — no-op/ошибка).
   - 2d. **Сервисная роль `BYPASSRLS`** для watchdog/catalog-sync/миграций,
     использующая `current_setting('app.tenant_id', true)` с обработкой NULL.
   - 2e. asyncpg-pool с `statement_cache_size=0` (готовится под pgbouncer
     заранее, см. Секцию 4).
3. **Кастомные поля:** `custom_field_definitions` + jsonb `custom` + валидация
   + индексы по типам (включая expression-индексы на `is_filterable`).
4. **Вынос стейта из процесса:** очередь → Redis (ARQ/RQ), scheduler → Redis
   JobStore.
5. **Процессная модель:** разделение web/worker/watchdog/scheduler под
   systemd, pgbouncer, `/health` + `/ready`.
6. **Кэширование метаданных.**
