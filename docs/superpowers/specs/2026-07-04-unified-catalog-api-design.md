# Единый каталог товаров CRM: реляционная схема + API v1

**Дата:** 2026-07-04
**Статус:** Draft (на ревью у пользователя)
**Связанные документы:** `2026-07-03-multitenancy-and-scalability-design.md`

## Контекст

Каталог товаров сейчас размазан по двум серверам и трём разным схемам:

- **`hhb_b2b.sku_catalog`** (478 товаров, 3 бренда: KYK/FKD/HHB) — плоская таблица,
  минимальные характеристики, общая для csbrg.ru и hhb. **Уже перенесена в CRM.**
- **`kyk.products`** (735 товаров, только KYK) — широкая плоская таблица с полными
  техническими характеристиками (rs_min, static_load, dynamic_load, rpm_oil,
  rpm_grease, seal_type, weight). Все 735 строк имеют заполненные характеристики.
  Живёт на сервере сайтов в БД `kyk`, схема `kyk`.

Решено: CRM (сервер 72.56.246.21) становится единым мастер-источником каталога.
Формат — **реляционный как у kyk** (с полными характеристиками). Сайты со временем
переводятся на чтение через API CRM; прямые запросы к своим БД убираются.

### Что НЕ входит (явный YAGNI / отложено)

- Переделка сайтов под новые эндпоинты (отдельная задача, не сейчас).
- Интеграция с 1С (отдельная задача — заполнитель `price_new`/`stock`).
- EAV/`product_specs` отдельной таблицей — плоские колонки проще.
- Несколько картинок на товар — одна `img`, как сейчас.
- Полнотекстовый поиск по характеристикам (Postgres FTS) — пока ILIKE.
- Мультитенантная фильтрация по владельцу-тенанту — каталог общий, не тенантный
  (см. основную спеку, секцию «catalog DB»).

---

## Секция 1. Схема данных

Три новые таблицы (`migration 003`). Полностью замещают `sku_catalog` для новой
логики; старая таблица временно остаётся, чтобы не сломать `/api/catalog/skus`.

### `brands`

```sql
CREATE TABLE brands (
    id      serial PRIMARY KEY,
    name    text NOT NULL UNIQUE,    -- "KYK", "FKD", "HHB"
    slug    text UNIQUE              -- для URL: "kyk", "fkd", "hhb"
);
```

### `categories` (с вложенностью)

```sql
CREATE TABLE categories (
    id        serial PRIMARY KEY,
    name      text NOT NULL,
    slug      text UNIQUE,
    title     text,                                   -- SEO-заголовок
    parent_id integer REFERENCES categories(id) ON DELETE SET NULL
);

CREATE INDEX idx_categories_parent ON categories (parent_id);
```

### `products` (единая плоская таблица со всеми характеристиками)

```sql
CREATE TABLE products (
    id            serial PRIMARY KEY,
    category_id   integer REFERENCES categories(id) ON DELETE SET NULL,
    brand_id      integer REFERENCES brands(id) ON DELETE SET NULL,
    code          text NOT NULL,                       -- "604ZZ" — аналог sku
    name          text NOT NULL,
    -- Технические характеристики (real → numeric для точности)
    weight        numeric(10,4),
    d             numeric(10,2),                       -- внутренний диаметр
    d_outer       numeric(10,2),
    b_width       numeric(10,2),
    rs_min        numeric(10,2),
    static_load   numeric(10,2),
    dynamic_load  numeric(10,2),
    rpm_oil       integer,
    rpm_grease    integer,
    seal_type     text,
    -- Цена/остаток (заполняются из 1С, пока nullable)
    price_old     numeric(12,2),
    price_new     numeric(12,2),
    stock         integer NOT NULL DEFAULT 0,
    is_active     boolean NOT NULL DEFAULT true,
    -- Доп. поле из hhb_b2b (массив сфер применения)
    application   text[] NOT NULL DEFAULT '{}',
    -- Изображение
    img           text,
    -- Метки времени (timestamptz, не bigint как в kyk — современнее)
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    -- Уникальность: code + brand (один и тот же code у разных брендов бывает)
    UNIQUE (code, brand_id)
);

CREATE INDEX idx_products_category ON products (category_id);
CREATE INDEX idx_products_brand    ON products (brand_id);
CREATE INDEX idx_products_active   ON products (is_active) WHERE is_active;
CREATE INDEX idx_products_code     ON products (code);
```

### Сознательные отличия от kyk.products

- `bigint created_at/updated_at` → `timestamptz` — современнее, совместимо с watchdog.
- `real` → `numeric(10,2)` — точность важна для цен/нагрузок, `real` (float4) теряет
  значащие цифры.
- **Формальные FK-констрейнты** — в kyk их не было, только логическая связь по id.
- `application text[]` добавлено (было только в hhb_b2b).
- `img text` добавлено (есть в hhb_b2b, нет в kyk).

### Что НЕ в схеме (YAGNI)

- `product_specs` отдельной EAV-таблицей — плоские колонки быстрее и проще.
- `product_images` (множественные картинки) — одна `img` как сейчас.
- `attributes` generic key-value — пока YAGNI.
- Полнотекстовый индекс — ILIKE хватает для подшипников.

---

## Секция 2. Миграция данных

Реализуется отдельным Python-скриптом `backend/scripts/import_catalog.py`, не SQL.
Запускается один раз вручную; идемпотентный (можно перезапускать).

### Источники → Приёмник

| Источник | Строк | Логика |
|---|---|---|
| `kyk.brands` (1 строка: KYK) | 1 | Прямой импорт id→id |
| Ручные бренды FKD, HHB | 2 | INSERT по name (берутся из существующих данных) |
| `kyk.categories` (9 строк) | 9 | Прямой импорт, сохраняя parent_id |
| `kyk.products` (735 строк) | 735 | Почти прямой импорт: все характеристики сохраняются, `created_at`/`updated_at` (unix bigint) → `timestamptz` |
| `hhb_b2b.sku_catalog` (478 строк, уже в CRM) | 478 | Трансформация: `sku`→`code`, `brand`→резолв `brand_id` по name, `category`→резолв/создание `category_id` по name, `d_inner`→`d`, `price`→`price_new`, характеристики NULL |

### Дубликаты и конфликты

`kyk.products` и `hhb_b2b.sku_catalog` **могут пересекаться** по `code`/`sku`
(например, "Подшипник 604 ZZ" есть и там, и там). Политика:

1. Сначала импортируем `kyk.products` (там характеристики полные) — они основные.
2. При импорте `hhb_b2b.sku_catalog` для каждой строки проверяем: есть ли уже
   товар с таким `code` + тем же `brand_id` в приёмнике?
   - **Если да** — пропускаем (kyk-версия приоритетнее, у неё есть характеристики).
   - **Если нет** — создаём (это товары FKD/HHB, которых нет в kyk).

Скрипт логирует количество: вставлено / пропущено (дубликаты) / ошибок.

---

## Секция 3. API v1

Новый роутер `routes/catalog_v1.py`. Префикс `/api/v1` чтобы не ломать
существующий `/api/catalog/skus` (он читает из старой `sku_catalog`).

### Эндпоинты

| Метод | Путь | Авторизация | Назначение |
|---|---|---|---|
| `GET` | `/api/v1/products` | публично | Список с фильтрами и пагинацией |
| `GET` | `/api/v1/products/{id}` | публично | Карточка со всеми характеристиками |
| `GET` | `/api/v1/brands` | публично | Список брендов |
| `GET` | `/api/v1/categories` | публично | Дерево категорий (с parent) |
| `GET` | `/api/v1/products/{id}/stock` | публично | Только остаток + цена (для виджетов наличия) |
| `POST` | `/api/v1/products/{id}/stock` | B2B-токен | Обновить остаток/цену (для 1С-агента) |

### `GET /api/v1/products` — параметры фильтрации

| Параметр | Тип | Пример | Описание |
|---|---|---|---|
| `brand` | string | `kyk` | Фильтр по slug бренда |
| `category` | string | `bearings` | Фильтр по slug категории |
| `search` | string | `604` | ILIKE по `code`/`name` |
| `d_min` / `d_max` | float | `4` / `20` | Диапазон внутреннего диаметра `d` |
| `d_outer_min` / `d_outer_max` | float | | Диапазон внешнего диаметра |
| `seal_type` | string | `Открытый` | Фильтр по типу уплотнения |
| `has_stock` | bool | `true` | Только ненулевые остатки |
| `is_active` | bool | `true` | По умолчанию `true` (не показывать неактивные) |
| `limit` | int | `50` | Пагинация, макс 200 |
| `offset` | int | `0` | Смещение |

**Ответ:**
```json
{
  "items": [
    {
      "id": 3,
      "code": "604",
      "name": "Подшипник роликовый 604",
      "brand": {"id": 1, "name": "KYK", "slug": "kyk"},
      "category": {"id": 3, "name": "Миниатюрные шарикоподшипники", "slug": "miniature_ball_bearings"},
      "d": 4, "d_outer": 12, "b_width": 4,
      "price_new": null,
      "stock": 0,
      "is_active": false
    }
  ],
  "total": 1213,
  "limit": 50,
  "offset": 0
}
```

В списочном эндпоинте характеристики **не** возвращаются (только базовые поля) —
для производительности. Полный набор — в `GET /api/v1/products/{id}`.

### `GET /api/v1/products/{id}` — карточка

Возвращает **все** поля товара, включая характеристики, `application[]`, `img`.

### Кэширование

- `GET /api/v1/brands` и `GET /api/v1/categories` — Redis, TTL 1 час, с
  инвалидацией при изменении (через `DEL crm:catalog:brands`).
- `GET /api/v1/products` (список) — без кэша, всегда свежий (фильтры динамические).
- `GET /api/v1/products/{id}` — Redis с коротким TTL (5 мин), инвалидация по
  `DEL crm:catalog:product:{id}` при обновлении stock/price.

### Обновление stock (для 1С)

`POST /api/v1/products/{id}/stock` — тело:
```json
{"stock": 142, "price_new": 350.00}
```
Любое поле опционально. После успешного обновления — инвалидация кэша карточки.
Авторизация — `verify_b2b_token` (Bearer), только для 1С-агента.

---

## Секция 4. Тестирование

TDD по тому же шаблону, что watchdog-план. Покрытие:

- Миграция 003 (создание таблиц, идемпотентность).
- Скрипт импорта (`import_catalog.py`) — на тестовой БД с фиктивными данными
  kyk + hhb: проверка количества, дедупликации, сохранения характеристик.
- `GET /api/v1/products` — фильтры (по бренду, категории, диапазону d,
  has_stock, search), пагинация, пустой результат.
- `GET /api/v1/products/{id}` — существующий + несуществующий (404).
- `GET /api/v1/brands`, `/categories` — структура, кэш-инвалидация.
- `POST /api/v1/products/{id}/stock` — успех с токеном, 401 без токена,
  обновление полей, инвалидация кэша.

---

## Порядок реализации

1. **Миграция 003** — создание таблиц `brands`, `categories`, `products`.
2. **Скрипт `import_catalog.py`** — импорт данных (запуск вручную один раз).
3. **API v1 роуты** — реализация эндпоинтов с фильтрами, TDD.
4. **Кэш метаданных** — Redis для brands/categories/product-card.
5. **Smoke-тест** на сервере — убедиться, что API отвечает реальными данными.
6. **(Отдельно, позже)** — перевод сайтов csbrg/kyk/hhb на чтение через API.

Старый `/api/catalog/skus` и таблица `sku_catalog` **не удаляются** до тех пор,
пока все сайты не перейдут на `/api/v1`.
