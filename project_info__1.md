# crmks — Codebase Overview (Explore findings: what I like / what I don’t)

## Summary
`crmks` is a single-page web app (Vue 3 + Pinia + Vue Router) backed by a FastAPI service that manages sales/CRM-related entities (clients, SKUs, proposals, leads, tasks, notes, calendar events) and also exposes an “AI chat” endpoint which can create/operate on those entities via server-side “tools”.  
The backend is designed to run in two modes: PostgreSQL (async pool + Redis-backed token store + background queue worker) and a local SQLite fallback (mostly synchronous DB access, queue/token features disabled depending on connectivity).  
Developers interact with it mainly through REST endpoints under `/api/*` plus `/docs` (FastAPI Swagger).

---

## Architecture
**Primary pattern:** monolithic-but-modular FastAPI router/services design + “tool registration” for the AI agent.  
The backend is split into:
- **Routers** (`crmks/backend/routes/*`) — HTTP endpoints grouped by domain.
- **Services** (`crmks/backend/services/*`) — business logic (e.g., `tasks_service`).
- **Cross-cutting infra**:
  - `crmks/backend/db.py` — DB connection + SQL dialect adaptation (Postgres vs SQLite).
  - `crmks/backend/token_store.py` — Redis token storage (async+sync APIs).
  - `crmks/backend/startup/db_init.py` — table creation/migrations + seed data.
  - `crmks/backend/ai_routes.py` + `crmks/backend/ai/*` — AI chat orchestration and tool registry.

**Execution start (backend):**
1. `crmks/backend/main.py` creates FastAPI with lifespan hooks.
2. On startup, it initializes:
   - database schema + seed/migrations (`startup_init_db()`)
   - queue worker (`init_queue_manager()`, only when Postgres is available)
   - async DB pool (`init_async_pool()`, only in Postgres mode)
   - Redis token store (`init_token_store()`)
3. `register_routes(app)` includes all domain routers + AI routers.
4. Requests are handled by routers, which call service functions. Auth is enforced by dependencies using Redis tokens.

**Execution start (frontend):**
1. `crmks/src/main.ts` boots Vue + Pinia + router.
2. `crmks/src/router/index.ts` defines role-based routes and a `roleGuard`.
3. UI state is handled through Pinia stores (`src/stores/*`) and domain-specific API clients (`src/api/*`, not inspected in this session).

---

## Directory Structure (annotated)
```
crmks/
├── src/                              — Vue 3 SPA
│   ├── main.ts                       — app bootstrap
│   ├── router/
│   │   ├── index.ts                 — routes + roleGuard
│   │   └── guards.ts               — role-based navigation guard (not read)
│   ├── stores/
│   │   ├── auth.ts                 — token/user state (login/logout/me)
│   │   └── tasks.ts                — tasks CRUD state via tasksApi
│   ├── api/                         — API client wrappers (not fully read)
│   └── components/
│       └── ai/
│           ├── AIAssistantPanel.vue — AI UI panel
│           └── ChatMessage.vue      — message rendering (not read)
│
└── backend/                          — FastAPI service
    ├── main.py                       — app + lifespan + middleware + route registration
    ├── routes/
    │   ├── index.py                 — auth/users/plans endpoints + search/email
    │   ├── tasks.py                 — /api/tasks endpoints (delegates to tasks_service)
    │   ├── ai_routes.py             — /api/ai/chat (agent wrapper)
    │   └── ... (many domain routers)
    ├── services/
    │   ├── tasks_service.py        — tasks business logic + PG/SQLite branches
    │   ├── queue_service.py        — queue manager init gating by Postgres availability
    │   └── ... (other domain services)
    ├── ai/
    │   ├── ai_agent.py              — run_agent entry point (not read)
    │   ├── ai_routes.py             — AI tool registry (not read)
    │   └── tools_*                — tool implementations (not read)
    ├── db.py                        — DB adapter (psycopg2 vs sqlite3) + q(sql) placeholder adaptation
    ├── db_async.py                  — asyncpg pool + fetch/execute helpers (Postgres only)
    ├── token_store.py              — Redis token storage + sync/async APIs
    ├── startup/
    │   ├── db_init.py              — table creation, migrations, seed data
    │   └── scheduler_startup.py   — scheduler bootstrap (not read)
    └── queue_manager.py            — background worker orchestration (not read)
```

---

## Key Abstractions

### DB layer + dialect adapter (`db.py`)
- **File**: `crmks/backend/db.py`
- **Responsibility**: Choose DB driver at runtime (`psycopg2` if reachable, else SQLite), provide `get_db()` and a `q(sql)` function that adapts SQL placeholders and `ILIKE`.
- **Interface**:
  - `get_db()` → returns a live connection for sync usage
  - `q(sql)` → adapts SQL for SQLite (`%s`→`?`, strips `RETURNING id`, and maps `ILIKE`→`LIKE`)
- **Lifecycle**: Connection created per call; closes per endpoint/service usage.
- **Used by**: Nearly all routers/services for sync DB calls; `db_async.py` also relies on `_use_pg` to decide behavior.

### Redis token store (`token_store.py`)
- **File**: `crmks/backend/token_store.py`
- **Responsibility**: Store `token -> user_id` with TTL and implement sliding refresh. Offers both async and sync APIs because parts of the backend are async and parts remain sync.
- **Interface**:
  - `init_token_store()` / `close_token_store()` — initializes both async+sync redis clients (or optionally fails fast)
  - `set_token_sync`, `get_token_sync`, `delete_token_sync`, `refresh_token_sync`
  - `set_token`, `get_token`, `delete_token`, `refresh_token`
- **Lifecycle**: Initialized in FastAPI lifespan (`main.py`), closed on shutdown.

### Auth dependency (`auth_deps.py`)
- **File**: `crmks/backend/auth_deps.py`
- **Responsibility**: Authenticate requests using `Authorization: Bearer <token>`, validate token in Redis, load user from DB, and apply sliding TTL refresh.
- **Interface**:
  - `get_current_user(request)` → sync auth dependency
  - `get_current_user_async(request)` → async auth dependency; falls back to `to_thread` for non-Postgres mode
- **Used by**:
  - `routes/index.py` for `Depends(get_current_user_dep)`
  - `routes/tasks.py` for async endpoints

### Queue gating (`services/queue_service.py`)
- **File**: `crmks/backend/services/queue_service.py`
- **Responsibility**: Start background queue worker only when Postgres is available; in SQLite mode it disables queue functionality.
- **Interface**:
  - `init_queue_manager()`
  - `get_queue_manager()`
- **Lifecycle**: Called at backend startup in `main.py` (sync).

### AI chat HTTP wrapper (`ai_routes.py`)
- **File**: `crmks/backend/ai_routes.py`
- **Responsibility**: Expose `POST /api/ai/chat`, parse frontend/new vs legacy request formats, ensure auth, and call `run_agent(...)`.
- **Interface**:
  - `@router.post("/chat") def ai_chat(body, current_user=Depends(...))`
- **Non-obvious point**: Uses a custom `_get_current_user_lazy()` instead of `auth_deps.get_current_user_async` to avoid cycles at startup and to support “multiple workers” behavior (it directly checks Redis and DB in a locally imported block).
- **Used by**: Frontend AI components (through API client, not read).

### Tasks HTTP router + service
- **Files**:
  - `crmks/backend/routes/tasks.py`
  - `crmks/backend/services/tasks_service.py`
- **Responsibility**:
  - Router: maps HTTP verbs to service calls (`list/create/update/delete/complete/my`)
  - Service: implements business rules and DB queries
- **Non-obvious point**: service contains two branches (`if _use_pg:` asyncpg queries, else sync sqlite3 queries). That means behavior and performance characteristics can differ materially across environments.

### Startup DB initialization/migrations/seed
- **File**: `crmks/backend/startup/db_init.py`
- **Responsibility**: Create tables (catalog, clients, proposals, tasks, notes, etc.), run lightweight “ALTER TABLE ADD COLUMN IF NOT EXISTS” migrations for missing columns, and seed initial rows if empty.
- **Non-obvious point**: The project runs “schema + seed” from application startup instead of a dedicated migration framework.

---

## Data Flow (primary paths)

### 1) Login → token → authenticated request
1. Client calls `POST /api/auth/login` (router: `crmks/backend/routes/index.py`).
2. Backend validates user/password with hashed passwords.
3. Backend creates a random token and stores it in Redis via `set_token_sync()` (`crmks/backend/token_store.py`).
4. Subsequent requests send `Authorization: Bearer <token>`.
5. Auth dependency reads token from Redis, refreshes TTL (sliding expiry), then loads user row from DB (`crmks/backend/auth_deps.py` or AI’s lazy auth).

### 2) Tasks management (CRUD)
1. Frontend calls `/api/tasks` (router: `crmks/backend/routes/tasks.py`).
2. Router delegates to `tasks_service` functions; each uses `_use_pg` to select asyncpg vs sqlite sync queries.
3. Service enforces “employee sees only assigned tasks” via `assigned_to = current_user["id"]` checks.
4. Updates and completion also enforce ownership (employee cannot operate on unassigned tasks).

### 3) AI chat
1. Frontend calls `POST /api/ai/chat` (router: `crmks/backend/ai_routes.py`).
2. Backend parses request:
   - new format: `messages[]` (uses last `user` message + builds history)
   - old format: `message` + `history`
3. Backend authenticates using `_get_current_user_lazy()`:
   - validate bearer token in Redis
   - refresh token TTL
   - load user in local DB cursor
4. Backend calls `run_agent(user_message, current_user, history, db_conn=None)`.
5. Server returns `reply`, plus `tool_calls` and `iterations` in a response model.

---

## Non-Obvious Behaviors & Design Decisions (plus what I like / dislike)

### What I like
- **Clear separation of routers and services** for domain logic: `routes/tasks.py` delegates almost entirely to `services/tasks_service.py`, keeping endpoints thin.
- **Deliberate dual DB strategy**: `db.py` + `q(sql)` + `_use_pg` allow running the same code against Postgres and SQLite. This makes local development possible without standing up Postgres (though some features are disabled).
- **Auth uses sliding TTL** implemented server-side (`refresh_token_sync`/`refresh_token_sync`) which matches real “session stays alive while active” behavior.
- **AI endpoint is designed for multiple frontend formats** (new `messages[]` vs legacy `message`/`history`) which reduces migration friction.
- **AI tool registration pattern**: `ai_routes.py` imports `ai_tools_users` and `ai_tools_leads` purely to ensure decorators run at import time—this is a common and pragmatic approach in tool-based agents.

### What I don’t like (or I’d fix/flag)
- **Duplicated auth logic**:
  - `auth_deps.py` provides sync/async auth dependencies.
  - `ai_routes.py` reimplements a “lazy auth” function with similar Redis+DB steps.
  This duplication increases the chance of subtle drift (e.g., different error messages, different refresh behavior, different edge-case handling).
- **Schema + seed are executed on every startup** via `startup_init_db()` (`db_init.py`).  
  Even though seeding checks `COUNT(*) == 0`, this approach couples runtime startup time and data correctness to application launch. In production, it’s usually better to separate migrations/seeding from runtime.
- **SQL dialect adaptation by string replacement** (`q(sql)`) is fragile:
  - It assumes every `%s` placeholder corresponds to a placeholder and that `ILIKE` only occurs in appropriate contexts.
  - It strips `RETURNING id` for SQLite by replacement, which can silently break if query text changes.
- **Mixed sync/async DB usage model**:
  - In Postgres mode, endpoints are async and use asyncpg in services.
  - In non-Postgres mode, endpoints still work but via sync sqlite connections.
  That’s fine, but it means correctness/performance bugs might show up only in one mode.
- **Potential parameter semantics bug risk in `tasks_service` mapping**:
  - `_map_task_row` assumes fixed column ordering (`r[9]` is status, `r[13]` is assignee name). If a SELECT changes, mapping silently corrupts the DTO.
  This is manageable but fragile without named-row mapping or explicit column lists per mapping function.
- **Security/operational considerations**:
  - CORS allows `allow_origins=["*"]` for the backend.
  - There is a rate limiter included (`rate_limiter.register_rate_limiter(app)`), but it wasn’t inspected in this session; still, “open CORS” plus bearer tokens can be a risky combination depending on deployment.
- **Project documentation gaps**:
  - `crmks/README.md` and root `README.md` are missing (the read attempt returned “File not found”).
  - The only operational “spec” appears to be code + startup behavior; that increases onboarding time.

---

## Module Reference (one-liners)
| File | Purpose |
|---|---|
| `crmks/backend/main.py` | FastAPI app setup + lifespan (DB init, queue init, async pool, Redis token store) + router registration |
| `crmks/backend/db.py` | DB driver selection (Postgres vs SQLite) + SQL placeholder adaptation (`q`) |
| `crmks/backend/db_async.py` | asyncpg pool + fetch/execute helpers (Postgres mode) |
| `crmks/backend/token_store.py` | Redis token storage with sync/async APIs + sliding expiration |
| `crmks/backend/auth_deps.py` | Request authentication dependency using Bearer token + user lookup |
| `crmks/backend/routes/index.py` | Auth (login/logout/me), user management, plans management, and `/api/search/email` |
| `crmks/backend/routes/tasks.py` | Tasks REST endpoints; thin router delegating to tasks_service |
| `crmks/backend/services/tasks_service.py` | Tasks business logic and DB queries with Postgres/SQLite branches |
| `crmks/backend/routes/ai_routes.py` (actually `crmks/backend/ai_routes.py`) | `POST /api/ai/chat` wrapper around `run_agent` |
| `crmks/backend/startup/db_init.py` | Schema creation + migrations + seed data at startup |

---

## Suggested Reading Order
1. `crmks/backend/main.py` — where startup and router registration happen (big picture).
2. `crmks/backend/db.py` — understand `_use_pg`, `get_db()`, and `q(sql)` dialect transformation.
3. `crmks/backend/token_store.py` + `crmks/backend/auth_deps.py` — how authentication works end-to-end.
4. `crmks/backend/services/tasks_service.py` — see the “two DB modes” approach and business rules for tasks.
5. `crmks/backend/ai_routes.py` — how the AI chat endpoint parses history and calls the agent/tools.
6. (If you touch AI tools) `crmks/backend/ai/ai_agent.py` and `crmks/backend/ai/tools_*.py` — how tool calls are interpreted and how they mutate domain state.

---

## Final answer: what I like vs what I don’t
- **I like:** modular FastAPI structure (routes → services), pragmatic dual DB mode, sliding-token auth, and backward-compatible AI request parsing.
- **I don’t like:** duplicated auth logic in AI route, fragile SQL string adaptation, startup-time schema/migrations/seed coupling, and lack of project-level documentation/README (so onboarding relies on reading code).
