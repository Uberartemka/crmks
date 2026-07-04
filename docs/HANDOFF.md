# 🎀 Хэндофф сессии 2026-07-04 (большая сессия)

> Точка возобновления. За сессию: 8 крупных задач (предыдущий блок) + Group C activation + **полноценный real-time чат сотрудников (Подсистема I) с деплоем на прод**.

## 📍 Проект

**frontcrm** — CRM для индустриальных дистрибьюторов подшипников. Vue 3 + FastAPI + PostgreSQL.

- **Репо:** [github.com/Uberartemka/crmks](https://github.com/Uberartemka/crmks) (ветка `main`, HEAD `e5b8d9e`)
- **Локальный путь:** `D:\Projects\frontcrm`
- **Прод:** **https://crmdot.ru** (домен + SSL Let's Encrypt, до 2026-10-02, авто-renew)
- **Тесты backend:** **154/154** (`cd backend && python -m pytest`)
- **Тесты frontend:** 5 (`npm run test` — vitest: useConfirm + useChatSocket)
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

### 10. 💬 Чат сотрудников (Подсистема I) — real-time messaging с нуля + деплой

Цель: «общий чат для всех сотрудников + каналы по отделам и темам → автономный документооборот». Это **мега-запрос**, декомпозированный на 3 подсистемы: I (real-time чат — выполнено), II (вложения — позже), III (документооборот со статусами — позже).

**Архитектура:** «запись через REST, доставка через WebSocket» (паттерн Slack/Mattermost). WS-auth через одноразовый ticket (Redis, атомарный GETDEL). Per-user rate-limit на Redis (INCR+EXPIRE, корректен на N воркерах). 3 типа каналов: `general` (все staff), `department` (по роли), `topic` (явные участники). Клиенты чат не видят.

- **Спека:** `docs/superpowers/specs/2026-07-04-chat-messaging-design.md` (+ 6 review-правок: GETDEL atomicity, PG partial-indexes вместо NULLS NOT DISTINCT, Redis rate-limit вместо IP-based, CHECK content<=10000, 400 на general/department members, запрет v-html)
- **План:** `docs/superpowers/plans/2026-07-04-chat-messaging.md` (16 TDD-задач, исполнено через subagent-driven-development)
- **Backend (миграция 009 + сервисы + REST + WS):**
  - Миграция 009: `channels`/`channel_members`/`messages` (BIGSERIAL, soft-delete, CHECK content)/`read_state` + засев general-канала. Partial UNIQUE indexes (PG13+-совместимо).
  - `services/chat_service.py` — channels (role-aware), messages (cursor pagination на `id`), read_state (GREATEST-монотонный курсор), membership (400 на general/department).
  - `services/chat_connections.py` — in-memory `CONNECTIONS` реестр + `fanout()` (единая точка расширения на multi-worker через Redis pub/sub).
  - `services/chat_redis.py` — `issue_ws_ticket`/`consume_ws_ticket` (GETDEL) + `allow_message` (INCR+EXPIRE, ~20 msg/мин).
  - `routes/chat.py` (11 REST endpoints) + `routes/chat_ws.py` (WS handler `/ws/chat`).
  - +33 теста (5 connections + 5 redis + 4 channels + 6 messages + 2 read-state + 4 membership + 3 ws + 4 members/users) → **154/154**.
- **Frontend (vue-advanced-chat интеграция):**
  - Подключён **vue-advanced-chat ^2.1.2** (web-component, Slack-подобный UI) с `register()` в `main.ts` + `isCustomElement` в `vite.config.ts`.
  - `composables/useChatAdapter.ts` — маппинг наш формат ↔ формат библиотеки (`toRoom`/`toMessage`).
  - `views/ChatView.vue` — обёртка над `<vue-advanced-chat>`, WS-connect on mount.
  - `components/chat/CreateChannelModal.vue` — создание topic-канала + выбор участников.
  - Старые `ChannelList`/`MessageList`/etc оставлены в коде (не удалял), ChatView их больше не использует.
- **Деплой на прод** (merge → push → ssh): `git pull` + `npm install` (vue-advanced-chat) + `npm run build` + restart `crmks-api`. nginx `/ws/` location добавлен (upgrade-хедеры, proxy_read_timeout 86400). Backup БД `/root/crmks_backup_20260704_175917.sql.gz`.
- **Зависимости:** `httpx-ws` (WS TestClient), `jsdom` (vitest env), `vue-advanced-chat` (UI).

**Endpoints чата (все под `Depends(get_current_user)`, staff-only):**
```
GET    /api/chat/channels                      — список видимых каналов (с members[])
POST   /api/chat/channels                      — создать topic (admin/manager)
GET    /api/chat/channels/{id}/messages        — история (cursor: ?before=&limit=)
POST   /api/chat/channels/{id}/messages        — отправить (rate-limit + WS fanout)
PATCH  /api/chat/messages/{id}                 — редактировать (только автор)
DELETE /api/chat/messages/{id}                 — soft-delete (автор/admin)
POST   /api/chat/channels/{id}/read            — отметить прочитанным (MAX(id) курсор)
GET    /api/chat/unread                        — {channel_id: count}
POST   /api/chat/channels/{id}/members         — добавить в topic
DELETE /api/chat/channels/{id}/members/{uid}   — убрать / покинуть (topic only, 400 на general/department)
GET    /api/chat/members?channel_id=           — участники канала (room-info панель)
GET    /api/chat/users                         — все staff (для invite-дропдауна)
POST   /api/chat/ws-ticket                     — одноразовый ticket (30с) для WS
WS     /ws/chat?ticket=                        — real-time push (message/typing/unread)
```

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
11. **⚠️ Чат: 4 uvicorn-воркера ломают real-time fan-out.** Прод крутит `--workers 4`, а `CONNECTIONS` реестр in-memory (per-worker). Сообщение дойдёт real-time только юзерам на **том же воркере**; остальные увидят его при reload истории. Это заложенная в спеку точка расширения — **Redis pub/sub bridge** между воркерами (15 строк в `fanout()`). Без него чат работает, но push не гарантирован мгновенным между всеми.
12. **WS-обработчик роняет сокет на malformed JSON** — `receive_json` кидает `JSONDecodeError`, ловится в generic `except`, соединение закрывается. Лучше ловить JSON-ошибки внутри цикла и продолжать. Некритично.
13. **Чат: `unread` key-type** — API возвращает `Record<string, number>`, store хранит `Record<number, number>`; TS пропустил через index-signature subtyping, runtime работает (JS coercion). Можно нормализовать в `loadUnread`.
14. **Чат: WS-singleton** — `useChatSocket` держит state в замыкании функции, поэтому WS открывается только когда юзер в `/.../chat`. Unread-бейджи вне чат-экрана не обновляются live.
15. **Чат: index-бандл раздут** — `vue-advanced-chat` подключён в `main.ts` (register), поэтому попал в main chunk (~728KB). Можно вынести в lazy/dynamic import для code-splitting.
16. **Redis локально отсутствует** (dev-машина) — message-тесты используют stub `allow_message` в fixtures (production-код чист, лимитер протестирован отдельно в `test_chat_redis.py`). На проде Redis есть (auth, PONG).

---

## 📋 Что осталось (в порядке приоритета)

> ✅ Пункты «Привязать client_id»/«Заполнить данные» (Group C) и **«Чат сотрудников» (Подсистема I)** выполнены. Список перенумерован.

| # | Задача | Сложность |
|---|---|---|
| 1 | **Чат: Redis pub/sub bridge** между воркерами — иначе real-time push только в пределах одного uvicorn-воркера (прод крутит `--workers 4`). ~15 строк в `fanout()`. | средняя |
| 2 | **Чат: Подсистема II (вложения)** — загрузка/хранение/раздача файлов, `attachment_id` в messages. Спека будет отдельная. | средняя |
| 3 | **Чат: Подсистема III (документооборот)** — карточки документов со статусами (черновик→согласование→подписан→архив), версии, привязка к клиенту/КП/заказу. | высокая |
| 4 | **Нормализация code-маппинга** — обогатить 357 старых KYK характеристиками (парсер артикула из «Подшипник HQ…+ KYK») | средняя |
| 5 | **Реальный Dashboard** с метриками (волна 2 UI) — сейчас это Workspace, не dashboard | средняя |
| 6 | **BaseBadge массово** по всем view + добить 4 нативных `confirm()` (`TaskBoard:107`, `NotesGrid:38`, `EventModal:69`, `ParserView:158`) → `useConfirm` | низкая |
| 7 | **Mobile-адаптив** (бургер-меню sidebar) | средняя |
| 8 | **DROP sku_catalog** (proposal-флоу не использует, безопасно после проверки) | низкая |
| 9 | **SERPAPI_KEY** в .env | тривиально |
| 10 | **B2B_ADMIN_TOKEN** — прописать свой в env (не дефолт) | тривиально |
| 11 | **Анализ разговоров** (STT + скоринг + извлечение) | высокая |
| 12 | **RAG по .md** (инженерная база знаний) | средняя |
| 13 | **Мультитенантность** (Plan 2: tenants + RLS) | высокая |
| 14 | **Retail/wholesale цены** (миграция) | средняя |
| 15 | **1С-интеграция** (writer остатков) | высокая |

---

## 🧭 Как войти в курс

- **«чат real-time между воркерами»** → Redis pub/sub bridge в `fanout()` (прод крутит `--workers 4`, сейчас push только в пределах одного воркера)
- **«чат вложения»** → Подсистема II (спека будет отдельная)
- **«чат документооборот»** → Подсистема III (статусы/версии/согласования)
- **«запусти сид»** → `cd backend && python -m scripts.seed_client_users_and_demo` (client-юзеры + demo orders/machinery/defects)
- **«давай dashboard»** → реальный экран с KPI (волна 2 UI)
- **«давай мультитенантность»** → writing-plans для Plan 2 (спека в `docs/superpowers/specs/2026-07-03-multitenancy-and-scalability-design.md`)
- **«нормализация code»** → обогащение 357 KYK
- **«поговорим про AI»** → анализ разговоров (STT+скоринг), RAG по инженерной базе — обсуждали как следующий большой трек
- или любую другую точку из списка

Все коммиты на main (`e5b8d9e`), тесты **154/154** зелёные, прод **https://crmdot.ru** живой (чат задеплоен, `/ws/` nginx location настроен).

---

## 📂 Полезные пути (чат + общий)

- **Спеки:** `docs/superpowers/specs/` — `2026-07-03-multitenancy-and-scalability-design.md`, `2026-07-04-chat-messaging-design.md` (чат I)
- **Планы:** `docs/superpowers/plans/` — `2026-07-04-chat-messaging.md` (16 TDD-задач, исполнено)
- **Чат-бэк:** `backend/services/chat_{service,connections,redis}.py`, `backend/routes/chat{,_ws}.py`, `backend/migrations/009_chat.sql`
- **Чат-фронт:** `src/composables/{useChatSocket,useChatAdapter}.ts`, `src/views/ChatView.vue`, `src/components/chat/`, `src/stores/chat.ts`
- **Backup БД (перед миграцией 009):** `/root/crmks_backup_20260704_175917.sql.gz` на проде

### ⚠️ nginx для WebSocket (прод) — `/ws/` location

Уже настроен в `/etc/nginx/sites-enabled/crmks` (между `/api/` и `/kp/`). Если пересоздавать конфиг — обязательно сохранить upgrade-хедеры, иначе WS за прокси не поднимется:
```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

