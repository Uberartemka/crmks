# 🎀 Хэндофф сессии 2026-07-04 (большая сессия)

> Точка возобновления. За эту сессию сделано 8 крупных задач + 1 доделка (Group C activation). CRM полностью переработана.

## 📍 Проект

**frontcrm** — CRM для индустриальных дистрибьюторов подшипников. Vue 3 + FastAPI + PostgreSQL.

- **Репо:** [github.com/Uberartemka/crmks](https://github.com/Uberartemka/crmks) (ветка `main`, HEAD `a57fff7`)
- **Локальный путь:** `D:\Projects\frontcrm`
- **Прод:** **https://crmdot.ru** (домен + SSL Let's Encrypt, до 2026-10-02, авто-renew)
- **Тесты backend:** **121/121** (`cd backend && python -m pytest`)
- **Тесты frontend:** 3 (`npm run test` — vitest, useConfirm)
- **Серверы:** CRM `72.56.246.21` (herodot), сайты `193.164.149.3`. Ключ `~/.ssh/kyk_server_key`.

**Вход в CRM:** `admin` / `4qszJO0sF8oyGR4h` (случайный пароль, задаётся через UI Personnel).

**Demo client-креды** (только dev/demo, после запуска сида — см. ниже; **ротация перед продом**):

| Логин | Пароль | Клиент |
|---|---|---|
| `agroeco` | `agroeco2026` | ООО «АГРОЭКО» |
| `econiva` | `econiva2026` | ООО «ЭКОНИВА-ЧЕРНОЗЕМЬЕ» |
| `miratorg` | `miratorg2026` | АПХ «МИРАТОРГ» |
| `rusagro` | `rusagro2026` | ГК «РУСАГРО» |
| `elevator` | `elevator2026` | Воронежский Элеватор |

---

## ✅ Что сделано за сессию (8 крупных задач + 1 доделка)

### 1. Импорт kyk.products (735 товаров)
- Скрипт `scripts/import_kyk_products.py` (staging → products, INSERT + ENRICH через COALESCE, case-insensitive brand)
- 735 товаров залиты: 478 → **1213 total** (563 active). Все 735 с характеристиками (rs_min/load/rpm/seal/weight)
- Delivery `deploy/import_kyk_products.sh` (COPY с JOIN с сайт-сервера → CSV → staging)
- **Нюанс:** форматы code в CRM («Подшипник HQ…+ KYK») и kyk («6203 ZZ») не совпали → 0 enrich, все 735 зашли как INSERT. Обогащение старых 357 KYK — отдельная задача.

### 2. Proposal-flow переведён на products
- Миграция 004: `proposal_items.sku_id` FK `sku_catalog CASCADE` → `products RESTRICT`
- 4 SQL-точки (proposals.py:137,346; email_service.py:51; ai_claude_agent.py:282) на `products + brands`
- `/api/catalog/skus` (список для /admin/proposals) переписан на products — **все 1213 SKU видны**
- 12 тестов proposal-флоу

### 3. GLM (BigModel) как primary AI
- `call_claude()` каскад: **GLM primary** (glm-4.5-flash), Anthropic/Kimi фолбэк
- `/api/ai/search` → GLM вместо DeepSeek (+ markdown-fence strip + timeout 30s)
- `kimi_client`/agent-loop → GLM через env (FC убран, function calling работает)
- Оптимизация промптов: `max_tokens=1024` (reasoning-модель!), JSON_SYSTEM_PROMPT, сжатие промптов
- **Ответ 18с → 6-8с** после оптимизации
- Ключ GLM: `960e47b3e0ec465ca28c1eb11ac7e0ce.vqtU6K0T11FeEiKt` (BigModel/Zhipu, free tier)

### 4. UI Волна 1 — компонентная база
- **BaseButton** (5 variants), **BaseBadge** (6 types, WCAG AA), **Toast** (vue-toastification@next, top-right, brand-themed), **ConfirmModal** + `useConfirm` composable (Promise-based, parallel-safe, a11y)
- Миграции: 4 alert()→toast (ProposalBuilder), 7 prompt()→модалки (NotesGrid, QuickAddBar, CallsView), мёртвые btn-* классы→BaseButton (TaskBoard, CallsView), confirm на удаление (ClientsView)
- Удалён мёртвый cva-Button.vue
- Vitest установлен, 3 теста useConfirm

### 5. UI Волна 2 — удаление моков (Группа A)
- `USE_MOCKS`/`mockEvents`/`localFallback`/`buildDemoPayload` полностью вычищены (−208 строк)
- events store, auth store, LoginView, CatalogView, PlanView — все на реальных API
- CatalogView: empty/error states + toast вместо фейк-фолбэка
- PlanView: empty-state для admin вместо demo-данных
- `VITE_USE_MOCKS` удалён из env.d.ts + .env + .env.example

### 6. Группа B — PlansView + AuditView
- Удалён мёртвый `admin/PlansView.vue` (не в роутере, −64 строки)
- Backend: фильтр `GET /api/notes?tag=audit` (опц. параметр, 3 теста)
- AuditView: загрузка последнего аудита + восстановление чек-листа + блок «История визитов» + toast

### 7. Группа C — 4 новых домена (с нуля)
- **Фундамент:** миграция 005 `users.client_id` (auth-user ↔ client-company связь) + `get_current_user` возвращает client_id
- **Defects** (миграция 006): CRUD `/api/defects`, DefectsView rewrite (BaseBadge статусов, toast, confirm)
- **Machinery** (миграция 007): CRUD `/api/machinery`, MachineryView rewrite (wear bar, BaseBadge)
- **Orders** (миграция 008): CRUD `/api/orders`, OrdersView rewrite (4-step tracker, BaseBadge)
- **Reports**: `/api/reports/metrics` (реальные метрики из orders/proposals: выручка, средний чек, конверсия КП, 6-мес динамика), ReportsView rewrite (0 хардкодов)
- Каждый домен: 5 backend-тестов (owner-check, client_id binding) = +20 тестов
- Паттерн: router → service → db, Depends(get_current_user), owner-check, FK-safe create, try/finally cleanup

### 8. Security + домен
- Demo-пароли удалены из LoginView.vue + db_init.py seed. Admin создаётся со **случайным паролем** (вывод в лог один раз). **Нет автосброса.**
- Бандл пересобран, demo-кредов в dist/ нет (grep чист)
- **Домен crmdot.ru** + SSL Let's Encrypt (certbot, до 2026-10-02)
- nginx `server_name crmdot.ru www.crmdot.ru 72.56.246.21`, HTTP→HTTPS редирект

### 9. Group C activation — client_id binding + demo-данные (доделка)
- **Backend:** `UserCreate`/`UserOut` (`schemas/auth.py`) получили опц. `client_id` (+ `client_name` в выдаче). `POST /api/users` сохраняет привязку и требует `client_id` для `role=client` (400 иначе). `GET /api/users` переписан с `LEFT JOIN clients` → возвращает `client_name` (admin без привязки даёт NULL, не пропадает из списка).
- **Frontend:** `PersonnelView` переписан — добавлена роль **«Клиент»** в селекте + дропдаун компании (грузится из `useClientsStore`), колонка «Компания» в таблице. Заодно переведён на `BaseButton` + `toast` (волна консистентности). `api/users.ts` + `stores/users.ts` пробрасывают `client_id`.
- **Скрипт сида** `scripts/seed_client_users_and_demo.py` (идемпотентный, каждый блок по `COUNT(*)==0`): 5 client-юзеров (фиксированные пароли, привязка по `bitrix_id` к seed-клиентам) + 6 demo orders (несколько со статусом delivered/paid/shipped за последние 6 мес → Reports оживает) + demo machinery (wear 30/55/82/88%) + demo defects. Запуск: `python -m scripts.seed_client_users_and_demo`.
- **Тесты:** `test_users_client_binding.py` (+5) → **121/121**. TDD: сначала красные, потом schema/route → зелёные.

---

## 🚨 Known issues / trade-offs

1. **Code-форматы CRM и kyk не совпадают** → enrich не сработал (0 совпадений по «Подшипник HQ…+ KYK» vs «6203 ZZ»). Все 735 зашли как INSERT. Нормализация — отдельная задача.
2. **GLM free tier** — может падать в 429 (rate limit). Concurrency не гарантирована. При оплате API — `GLM_API_KEY` меняется в `.env`, код не трогать.
3. **`B2B_ADMIN_TOKEN` дефолт** в `auth_deps.py` — `hhb_b2b_secret_token_2026`. На проде env может быть не задан → работает дефолт (публичен в коде). Стоит прописать свой.
4. **`sku_catalog` не дропнута** — proposal-флоу её не использует, но таблица осталась. Безопасно удалить после проверки.
5. **SERPAPI_KEY = REPLACE_ME** — не используется в основном флоу.
6. **db_init duplicate-noise** в api.log (`relation "defects" already exists`) — db_init и миграции работают параллельно; косметика.
7. **Reports метрики = 0** на чистой БД. После запуска `seed_client_users_and_demo.py` оживают (есть orders со статусом delivered/paid/shipped за последние 6 мес). На проде без сида — по-прежнему 0, пока нет реальных заказов.
8. **Orders/Machinery/Defects** заполняются сидом (`seed_client_users_and_demo.py`) на dev/demo. Client-юзеры создаются там же и привязываются к компаниям. На проде — заводить через UI Personnel (теперь поддерживает роль `client` + выбор компании).
9. **Reports `period` не валидируется** — неизвестное значение молча fallback на month. Можно добавить 400.
10. **Demo client-пароли фиксированы** (`agroeco2026` и т.д.) — только dev/demo. Перед любым проду-использованием ротация обязательна.

---

## 📋 Что осталось (в порядке приоритета)

> ✅ Пункты «Привязать client_id» и «Заполнить данные» выполнены (Group C activation, см. ниже). Список перенумерован.

| # | Задача | Сложность |
|---|---|---|
| 1 | **Нормализация code-маппинга** — обогатить 357 старых KYK характеристиками (парсер артикула из «Подшипник HQ…+ KYK») | средняя |
| 2 | **Реальный Dashboard** с метриками (волна 2 UI) — сейчас это Workspace, не dashboard | средняя |
| 3 | **BaseBadge массово** по всем view (Clients/Leads/Catalog/админ Calls статусы) + добить 4 нативных `confirm()` (`TaskBoard:107`, `NotesGrid:38`, `EventModal:69`, `ParserView:158`) → `useConfirm` | низкая |
| 4 | **Mobile-адаптив** (бургер-меню sidebar) | средняя |
| 5 | **DROP sku_catalog** (proposal-флоу не использует, безопасно после проверки) | низкая |
| 6 | **SERPAPI_KEY** в .env | тривиально |
| 7 | **B2B_ADMIN_TOKEN** — прописать свой в env (не дефолт) | тривиально |
| 8 | **Анализ разговоров** (STT + скоринг + извлечение) | высокая |
| 9 | **RAG по .md** (инженерная база знаний) | средняя |
| 10 | **Мультитенантность** (Plan 2: tenants + RLS) | высокая |
| 11 | **Retail/wholesale цены** (миграция) | средняя |
| 12 | **1С-интеграция** (writer остатков) | высокая |

---

## 🧭 Как войти в курс

- **«запусти сид»** → `cd backend && python -m scripts.seed_client_users_and_demo` (создаст client-юзеров + demo orders/machinery/defects, идемпотентно)
- **«давай dashboard»** → реальный экран с KPI (волна 2 UI)
- **«давай мультитенантность»** → writing-plans для Plan 2 (спека уже в `docs/superpowers/specs/2026-07-03-multitenancy-and-scalability-design.md`)
- **«нормализация code»** → обогащение 357 KYK
- **«поговорим про AI»** → анализ разговоров (STT+скоринг), RAG по инженерной базе — обсуждали как следующий большой трек
- или любую другую точку из списка

Все коммиты на main, тесты **121/121** зелёные, прод **https://crmdot.ru** живой.
