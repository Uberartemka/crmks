# 🎀 Хэндофф сессии 2026-07-04 (большая сессия)

> Точка возобновления. За эту сессию сделано 8 крупных задач. CRM полностью переработана.

## 📍 Проект

**frontcrm** — CRM для индустриальных дистрибьюторов подшипников. Vue 3 + FastAPI + PostgreSQL.

- **Репо:** [github.com/Uberartemka/crmks](https://github.com/Uberartemka/crmks) (ветка `main`, HEAD `a57fff7`)
- **Локальный путь:** `D:\Projects\frontcrm`
- **Прод:** **https://crmdot.ru** (домен + SSL Let's Encrypt, до 2026-10-02, авто-renew)
- **Тесты backend:** **116/116** (`cd backend && python -m pytest`)
- **Тесты frontend:** 3 (`npm run test` — vitest, useConfirm)
- **Серверы:** CRM `72.56.246.21` (herodot), сайты `193.164.149.3`. Ключ `~/.ssh/kyk_server_key`.

**Вход в CRM:** `admin` / `4qszJO0sF8oyGR4h` (случайный пароль, задаётся через UI Personnel). **Demo-креды удалены.**

---

## ✅ Что сделано за сессию (8 крупных задач)

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

---

## 🚨 Known issues / trade-offs

1. **Code-форматы CRM и kyk не совпадают** → enrich не сработал (0 совпадений по «Подшипник HQ…+ KYK» vs «6203 ZZ»). Все 735 зашли как INSERT. Нормализация — отдельная задача.
2. **GLM free tier** — может падать в 429 (rate limit). Concurrency не гарантирована. При оплате API — `GLM_API_KEY` меняется в `.env`, код не трогать.
3. **`B2B_ADMIN_TOKEN` дефолт** в `auth_deps.py` — `hhb_b2b_secret_token_2026`. На проде env может быть не задан → работает дефолт (публичен в коде). Стоит прописать свой.
4. **`sku_catalog` не дропнута** — proposal-флоу её не использует, но таблица осталась. Безопасно удалить после проверки.
5. **SERPAPI_KEY = REPLACE_ME** — не используется в основном флоу.
6. **db_init duplicate-noise** в api.log (`relation "defects" already exists`) — db_init и миграции работают параллельно; косметика.
7. **Reports метрики = 0** — правильно (нет доставленных заказов). Оживут когда появятся orders со статусом delivered/paid/shipped.
8. **Orders/Machinery/Defects пустые** — таблицы свежие, данных нет. Нужно заводить через UI (admin может создавать от имени client_id; client видит свои после привязки client_id в users).
9. **Reports `period` не валидируется** — неизвестное значение молча fallback на month. Можно добавить 400.

---

## 📋 Что осталось (в порядке приоритета)

| # | Задача | Сложность |
|---|---|---|
| 1 | **Привязать client_id** существующим юзерам (сейчас только admin). Создать client-юзеров + привязать к компаниям через `UPDATE users SET client_id=...`. Без этого client-экраны (Orders/Machinery/Defects) недоступны client-роли. | средняя |
| 2 | **Заполнить данные** — создать тестовые orders/machinery/defects (через UI или скрипт), чтобы Reports показывал реальные цифры | средняя |
| 3 | **Нормализация code-маппинга** — обогатить 357 старых KYK характеристиками (парсер артикула из «Подшипник HQ…+ KYK») | средняя |
| 4 | **Реальный Dashboard** с метриками (волна 2 UI) — сейчас это Workspace, не dashboard | средняя |
| 5 | **BaseBadge массово** по всем view (Clients/Leads/Catalog статусы) | низкая |
| 6 | **Mobile-адаптив** (бургер-меню sidebar) | средняя |
| 7 | **DROP sku_catalog** (proposal-флоу не использует, безопасно после проверки) | низкая |
| 8 | **SERPAPI_KEY** в .env | тривиально |
| 9 | **B2B_ADMIN_TOKEN** — прописать свой в env (не дефолт) | тривиально |
| 10 | **Анализ разговоров** (STT + скоринг + извлечение) | высокая |
| 11 | **RAG по .md** (инженерная база знаний) | средняя |
| 12 | **Мультитенантность** (Plan 2: tenants + RLS) | высокая |
| 13 | **Retail/wholesale цены** (миграция) | средняя |
| 14 | **1С-интеграция** (writer остатков) | высокая |

---

## 🧭 Как войти в курс

- **«привяжи client_id»** → создам client-юзеров + UPDATE users SET client_id, проверю что client-экраны работают
- **«заполни данные»** → скрипт сидинга orders/machinery/defects для демо
- **«давай dashboard»** → реальный экран с KPI (волна 2 UI)
- **«давай мультитенантность»** → writing-plans для Plan 2
- **«нормализация code»** → обогащение 357 KYK
- или любую другую точку из списка

Все коммиты на main, тесты **116/116** зелёные, прод **https://crmdot.ru** живой.
