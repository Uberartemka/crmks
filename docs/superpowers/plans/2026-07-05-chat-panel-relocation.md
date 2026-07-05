# Переезд чата в правую панель (Подсистема A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести командный чат с отдельной страницы `/chat` в правую панель `WorkspaceLayout` (на место AI-панели), чтобы чат был виден на всех страницах workspace и открывался кнопкой справа внизу.

**Architecture:** Чисто frontend — без backend, без миграций. Создаём `ChatPanel.vue` (обёртка над vue-advanced-chat, логика перенесена из `ChatView.vue`), встраиваем в `WorkspaceLayout` вместо `AIAssistantPanel`, убираем `/chat` из роутера (с редиректом на dashboard), убираем пункт «Чат» из sidebar, удаляем `ChatView.vue`. Бонус: `username-options: {minUsers: 2}` для отображения имени отправителя.

**Tech Stack:** Vue 3 + TypeScript + vue-advanced-chat + Pinia + vue-router + vitest.

**Spec:** `docs/superpowers/specs/2026-07-05-chat-panel-relocation-design.md`

---

## File Structure

**Frontend (create + modify + delete):**
- `src/components/chat/ChatPanel.vue` (create) — обёртка над vue-advanced-chat для узкой панели. Перенос логики из ChatView.
- `src/layouts/WorkspaceLayout.vue` (modify) — замена `AIAssistantPanel` → `ChatPanel`, FAB «AI» → «Чат», isStaff gate.
- `src/components/sidebar/AppSidebar.vue` (modify) — убрать 3 пункта «Чат» (admin/manager/employee).
- `src/router/index.ts` (modify) — убрать 3 `{ path: 'chat', ... }` + добавить 3 редиректа.
- `src/views/ChatView.vue` (delete) — логика перенесена в ChatPanel.
- `src/components/chat/ChatPanel.test.ts` (create) — frontend тесты.
- `src/components/ai/AIAssistantPanel.vue` — НЕ удаляем (dead code, для Подсистемы B).

**Backend: без изменений. Миграций нет.**

---

## Task 1: Создать `ChatPanel.vue` (перенос логики из ChatView)

**Files:**
- Create: `src/components/chat/ChatPanel.vue`

- [ ] **Step 1: Создать `src/components/chat/ChatPanel.vue`**

Это перенос логики из `src/views/ChatView.vue` (который мы прочтём в шаге 2 для сверки), обёрнутый в `aside w-[360px]` с header и кнопкой закрытия. Плюс `usernameOptions` (новое — для имени отправителя).

```vue
<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useChatSocket } from '@/composables/useChatSocket'
import { chatApi } from '@/api/chat'
import { toRoom, toMessage } from '@/composables/useChatAdapter'
import CreateChannelModal from '@/components/chat/CreateChannelModal.vue'
import { X } from 'lucide-vue-next'

const emit = defineEmits<{ close: [] }>()

const store = useChatStore()
const auth = useAuthStore()
const { connect, onMessage } = useChatSocket()

const messagesLoaded = ref(true)
const showCreateModal = ref(false)

const currentUserId = computed(() => String(auth.user?.id ?? 0))
const rooms = computed(() =>
  store.channels.map((c) => toRoom(c as any, store.unread[c.id] ?? 0)),
)
const messages = computed(() => store.activeMessages.map((m) => toMessage(m as any)))
const canCreate = computed(() => auth.role === 'admin' || auth.role === 'manager')

// Имя отправителя видно при ≥2 участников (вместо дефолта VAC ≥3).
// currentUser:false — своё собственное имя не показываем.
const usernameOptions = { minUsers: 2, currentUser: false }

const wsBase = import.meta.env.DEV
  ? 'ws://localhost:8000/ws/chat'
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/chat`

onMounted(async () => {
  await store.loadChannels()
  await store.loadUnread()
  if (store.activeChannelId) {
    await store.loadHistory(store.activeChannelId)
    messagesLoaded.value = true
  }
  try {
    const { data } = await chatApi.wsTicket()
    connect(wsBase, data.ticket)
    onMessage((msg) => {
      if (msg.type === 'message') store.onIncomingMessage(msg.message)
      else if (msg.type === 'unread') store.onUnread(msg.channel_id)
      else if (msg.type === 'typing') store.onTyping(msg.channel_id, msg.user_id)
    })
  } catch (e) {
    console.warn('chat WS connect failed', e)
  }
})

function onSend(event: any) {
  const { content, roomId, replyMessage } = event.detail[0]
  const replyToId = replyMessage?._id ? Number(replyMessage._id) : undefined
  store.sendMessage(Number(roomId), content, replyToId)
}

function onReply(_event: any) {
  // vue-advanced-chat handles the reply UX itself; replyMessage comes back in onSend.
}

async function onFetch(event: any) {
  const { room, options } = event.detail[0]
  const channelId = Number(room.roomId)
  messagesLoaded.value = false
  if (options?.reset) {
    store.setActive(channelId)
    await store.loadHistory(channelId)
  } else {
    const msgs = store.messagesByChannel[channelId] ?? []
    const before = msgs.length ? msgs[0].id : undefined
    await store.loadHistory(channelId, before)
  }
  messagesLoaded.value = true
}

function openCreateModal() {
  showCreateModal.value = true
}

async function onChannelCreated() {
  showCreateModal.value = false
  await store.loadChannels()
  await store.loadUnread()
}
</script>

<template>
  <aside class="flex flex-col h-full bg-slate-50 border-l border-slate-200 shrink-0 w-[360px]">
    <header class="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-white">
      <h3 class="font-semibold text-sm">Чат команды</h3>
      <button
        class="p-1 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-800 transition-colors"
        title="Закрыть"
        @click="emit('close')"
      >
        <X :size="14" />
      </button>
    </header>
    <div class="flex-1 overflow-hidden">
      <vue-advanced-chat
        :current-user-id="currentUserId"
        :rooms="rooms"
        :messages="messages"
        :rooms-loaded="true"
        :messages-loaded="messagesLoaded"
        :add-room-enabled="canCreate"
        :room-info-enabled="true"
        :show-search="false"
        :show-files="false"
        :show-audio="false"
        :textarea-action-enabled="false"
        :username-options="usernameOptions"
        lang="ru"
        height="100%"
        @send-message="onSend"
        @fetch-messages="onFetch"
        @add-room="openCreateModal"
        @message-reply="onReply"
      />
    </div>
    <CreateChannelModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @created="onChannelCreated"
    />
  </aside>
</template>
```

- [ ] **Step 2: Сверить с текущим `src/views/ChatView.vue`**

Прочитать `src/views/ChatView.vue` и убедиться, что вся логика (onMounted, onSend, onReply, onFetch, openCreateModal, onChannelCreated, computed-свойства) перенесена в ChatPanel без потерь. Различия:
- ChatPanel имеет `emit('close')` и header с кнопкой X (новое).
- ChatPanel добавил `usernameOptions` (новое).
- ChatPanel обёрнут в `<aside w-[360px]>` вместо `<div class="h-full">`.

Run: `cat src/views/ChatView.vue` (своеrо рода ревью переноса).

- [ ] **Step 3: Verify build (ChatPanel пока нигде не используется, но должен компилироваться)**

Run: `npm run build`
Expected: `✓ built`. ChatPanel не импортируется ещё, но Vite его не собирает, пока не импортируют — поэтому build пройдёт (ошибки TS в неиспользуемом файле Vite может не поймать). Дополнительная проверка через vue-tsc будет в Task 6.

- [ ] **Step 4: Commit**

```bash
git add src/components/chat/ChatPanel.vue
git commit -m "feat(chat-fe): ChatPanel component (logic relocated from ChatView, +usernameOptions)"
```

---

## Task 2: Изменить `WorkspaceLayout.vue` — AI → Chat

**Files:**
- Modify: `src/layouts/WorkspaceLayout.vue` (полная замена содержимого)

- [ ] **Step 1: Прочитать текущий WorkspaceLayout для сверки**

Run: `cat src/layouts/WorkspaceLayout.vue`

Запомнить текущую структуру: `AppSidebar` + `<main><RouterView/></main>` + `AIAssistantPanel v-show="isAiOpen"` + FAB «AI» (показывается только на /dashboard после Bug 1 фикса).

- [ ] **Step 2: Полностью заменить содержимое `src/layouts/WorkspaceLayout.vue`**

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()
const chatOpen = ref(false)

// Чат-панель доступна только staff (не клиентам) — клиенты чат не видят.
const isStaff = computed(() => Boolean(auth.role) && auth.role !== 'client')

// FAB-кнопка видна на дашбордах (как раньше AI), только для staff.
const showChatFab = computed(() => isStaff.value && route.path.endsWith('/dashboard'))

function openChat() {
  chatOpen.value = true
}

function closeChat() {
  chatOpen.value = false
}
</script>

<template>
  <div class="flex h-full">
    <AppSidebar />

    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>

    <ChatPanel v-if="isStaff" v-show="chatOpen" @close="closeChat" />

    <button
      v-if="!chatOpen && showChatFab"
      class="fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full bg-brand-600 text-white px-4 py-2 shadow-lg border border-black/10 hover:bg-brand-700"
      @click="openChat"
      title="Открыть чат команды"
    >
      <span class="text-sm font-semibold">Чат</span>
    </button>
  </div>
</template>
```

**Ключевые изменения vs текущего:**
- `import AIAssistantPanel` → `import ChatPanel from '@/components/chat/ChatPanel.vue'`
- `import { useAuthStore }` добавлен (для isStaff gate)
- `isAiOpen` → `chatOpen`
- `openAi/closeAi` → `openChat/closeChat`
- FAB: текст «AI ✨» → «Чат», title «Открыть AI ассистента» → «Открыть чат команды»
- Добавлен `isStaff` computed и `v-if="isStaff"` на ChatPanel
- `<AIAssistantPanel @close="closeAi" />` → `<ChatPanel @close="closeChat" />`

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: `✓ built`. AIAssistantPanel больше не импортируется здесь, ChatPanel импортируется.

- [ ] **Step 4: Commit**

```bash
git add src/layouts/WorkspaceLayout.vue
git commit -m "feat(chat-fe): WorkspaceLayout — replace AIAssistantPanel with ChatPanel"
```

---

## Task 3: Убрать пункт «Чат» из sidebar (3 роли)

**Files:**
- Modify: `src/components/sidebar/AppSidebar.vue` (3 строки удалить + неиспользуемый импорт)

- [ ] **Step 1: Убрать 3 строки `{ to: \`${base}/chat\`, ... }`**

В `src/components/sidebar/AppSidebar.vue` удалить три строки (они в массивах menu для admin/manager/employee):

Строка в admin-блоке (после `calendar`):
```typescript
    { to: `${base}/calendar`, label: 'Календарь', icon: CalendarDays },
    { to: `${base}/chat`, label: 'Чат', icon: MessageSquare },   // ← УДАЛИТЬ
    { to: `${base}/personnel`, label: 'Персонал', icon: PersonStanding },
```

Строка в manager-блоке:
```typescript
    { to: `${base}/calendar`, label: 'Календарь', icon: CalendarDays },
    { to: `${base}/chat`, label: 'Чат', icon: MessageSquare },   // ← УДАЛИТЬ
    { to: `${base}/proposal-history`, label: 'История КП', icon: History },
```

Строка в employee-блоке:
```typescript
  if (auth.role === 'employee') return [
    ...common,
    { to: `${base}/plan`, label: 'Мой план', icon: ListChecks },
    { to: `${base}/chat`, label: 'Чат', icon: MessageSquare },   // ← УДАЛИТЬ
  ]
```

- [ ] **Step 2: Убрать неиспользуемый импорт `MessageSquare`**

После удаления строк `MessageSquare` больше не используется. В import-блоке (строки 5-9) убрать `MessageSquare`:

Было:
```typescript
import {
  LayoutDashboard, ListChecks, Users, FileText, LogOut,
  BarChart3, Search, Briefcase, Phone, PersonStanding, ShoppingCart,
  Calculator, Cog, ClipboardList, History, Send, CalendarDays, MessageSquare
} from 'lucide-vue-next'
```

Стало:
```typescript
import {
  LayoutDashboard, ListChecks, Users, FileText, LogOut,
  BarChart3, Search, Briefcase, Phone, PersonStanding, ShoppingCart,
  Calculator, Cog, ClipboardList, History, Send, CalendarDays
} from 'lucide-vue-next'
```

- [ ] **Step 3: Verify build (TS должен заметить неиспользуемый импорт, если не убрали)**

Run: `npm run build`
Expected: `✓ built`. Если забыли убрать `MessageSquare` — будет TS-warning/ошибка «unused import».

- [ ] **Step 4: Commit**

```bash
git add src/components/sidebar/AppSidebar.vue
git commit -m "refactor(chat-fe): remove '/chat' menu items from sidebar (chat now in right panel)"
```

---

## Task 4: Убрать `/chat` из роутера + добавить редиректы

**Files:**
- Modify: `src/router/index.ts` (3 замены)

- [ ] **Step 1: Прочитать текущий router для точных строк**

Run: `cat src/router/index.ts`

Найти 3 строки `{ path: 'chat', component: () => import('@/views/ChatView.vue') }` — они внутри children-блоков admin (строка ~23), manager (~47), employee (~60).

- [ ] **Step 2: Заменить каждую `{ path: 'chat', component: ... }` на редирект**

В каждом из трёх children-блоков (admin/manager/employee) заменить:
```typescript
      { path: 'chat', component: () => import('@/views/ChatView.vue') },
```
на:
```typescript
      { path: 'chat', redirect: 'dashboard' },
```

(Относительный redirect внутри layout-children: `/admin/chat` → `/admin/dashboard`, и т.д. — vue-router разрезает относительный путь относительно родителя.)

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: `✓ built`. ChatView.vue больше не импортируется в роутере (lazy import убран), но файл ещё существует — не страшно.

- [ ] **Step 4: Commit**

```bash
git add src/router/index.ts
git commit -m "refactor(chat-fe): replace /chat routes with redirect to /dashboard"
```

---

## Task 5: Удалить `src/views/ChatView.vue`

**Files:**
- Delete: `src/views/ChatView.vue`

- [ ] **Step 1: Подтвердить, что ChatView больше нигде не импортируется**

Run: `grep -rn "ChatView" src/ --include="*.ts" --include="*.vue"`
Expected: пусто (после Task 4 роутер больше не импортирует ChatView). Если есть упоминания — STOP, разобрать их сначала.

- [ ] **Step 2: Удалить файл**

Run: `rm src/views/ChatView.vue`

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: `✓ built`. Без ссылок на ChatView ничего не должно сломаться.

- [ ] **Step 4: Commit**

```bash
git add -A src/views/ChatView.vue
git commit -m "chore(chat-fe): remove ChatView.vue (logic relocated to ChatPanel)"
```

(Примечание: `git add -A` подхватит удаление; `git rm` тоже сработает.)

---

## Task 6: Frontend тесты — ChatPanel + WorkspaceLayout isStaff gate

**Files:**
- Create: `src/components/chat/ChatPanel.test.ts`

- [ ] **Step 1: Создать тест-файл**

Создать `src/components/chat/ChatPanel.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPanel from './ChatPanel.vue'

// Stub vue-advanced-chat (web component — не монтируем настоящий)
// и CreateChannelModal (не нужен для unit-теста)
const globalStubs = {
  stubs: {
    'vue-advanced-chat': { template: '<div class="vac-stub" />' },
    CreateChannelModal: { template: '<div />' },
  },
}

// Mock useChatSocket (возвращает пустые функции, чтобы onMounted не падал)
vi.mock('@/composables/useChatSocket', () => ({
  useChatSocket: () => ({
    connect: vi.fn(),
    onMessage: vi.fn(),
  }),
}))

// Mock chatApi (не делаем реальных запросов)
vi.mock('@/api/chat', () => ({
  chatApi: {
    wsTicket: vi.fn().mockResolvedValue({ data: { ticket: 'test-ticket' } }),
    listChannels: vi.fn().mockResolvedValue({ data: [] }),
    listMessages: vi.fn().mockResolvedValue({ data: [] }),
    unread: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

describe('ChatPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('монтируется и рендерит header "Чат команды"', async () => {
    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    expect(wrapper.text()).toContain('Чат команды')
  })

  it('эмитит close при клике на кнопку X', async () => {
    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    const closeBtn = wrapper.find('button[title="Закрыть"]')
    expect(closeBtn.exists()).toBe(true)
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('close')!.length).toBe(1)
  })
})
```

- [ ] **Step 2: Проверить, установлен ли @vue/test-utils**

Run: `cat package.json | grep test-utils`

Если `@vue/test-utils` нет в devDependencies — установить:
```bash
npm install -D @vue/test-utils
```

(Если уже есть — пропустить установку.)

- [ ] **Step 3: Run new tests**

Run: `npm test -- ChatPanel`
Expected: PASS (2 теста). Если `@vue/test-utils` не установлен — упадёт с «Cannot find module '@vue/test-utils'», тогда Step 2 обязателен.

- [ ] **Step 4: Run all frontend tests (regression)**

Run: `npm test`
Expected: PASS. Раньше 9; теперь 9 + 2 = **11** (если @vue/test-utils был) или придётся установить сначала.

- [ ] **Step 5: Commit**

```bash
git add src/components/chat/ChatPanel.test.ts package.json package-lock.json
git commit -m "test(chat-fe): ChatPanel mount + close event (with @vue/test-utils)"
```

(Если package.json не менялся — `git add` только тест-файла.)

---

## Task 7: Финальная проверка — build + полный прогон + ручной smoke

**Files:** none (verification only)

- [ ] **Step 1: Full frontend test suite**

Run: `npm test`
Expected: **11 passed** (9 ранее + 2 новых ChatPanel).

- [ ] **Step 2: Production build (с vue-tsc проверкой типов)**

Run: `npm run build`
Expected: `✓ built`, no TS errors. Особое внимание:
- ChatPanel.vue компилируется
- WorkspaceLayout.vue компилируется (ChatPanel импорт резолвится)
- AppSidebar.vue без unused MessageSquare
- ChatView.vue удалён, нигде не ссылается

- [ ] **Step 3: Backend regression (не должен измениться)**

Run: `cd backend && python -m pytest -q`
Expected: **174 passed** (без изменений — backend не трогали).

- [ ] **Step 4: Ручной smoke (выполняет пользователь в браузере)**

Открыть `/admin/dashboard`:
1. Справа внизу FAB «Чат» (не «AI») → кликнуть → открывается панель w-[360px]
2. Header «Чат команды» + кнопка X
3. Каналы видны, переключаются, активный канал открывается
4. Сообщение отправляется и появляется
5. **Имя отправителя видно** над сообщением (usernameOptions minUsers:2)
6. Перейти на `/admin/proposals` → панель остаётся открытой
7. Кликнуть X → панель закрывается, снова FAB
8. Ввести `/admin/chat` в URL → редирект на `/admin/dashboard`
9. В sidebar НЕТ пункта «Чат»
10. **VAC в 360px читаем** — если rooms-list и messages делят место криво, отметить для CSS-override (отдельная задача)
11. Зайти как client (если есть тестовый) → FAB «Чат» НЕ виден, панель не открывается

> Этот шаг требует живого браузера — ассистент не может его выполнить. Пользователь подтверждает визуально.

---

## Task 8: Деплой на прод

> Выполняется после визуального smoke-подтверждения от пользователя.

- [ ] **Step 1: Push в origin**

```bash
git push origin main
```

- [ ] **Step 2: Pull + build на проде (без backend restart — backend не менялся)**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'cd /var/www/crmks && git pull origin main && npm run build && echo "build OK"'
```

- [ ] **Step 3: Smoke на проде**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'curl -s -o /dev/null -w "GET https://crmdot.ru/ → HTTP %{http_code}\n" https://crmdot.ru/'
```
Expected: HTTP 200 (фронт раздаётся). Пользователь открывает `https://crmdot.ru/admin/dashboard` и проходит те же шаги что в Task 7 Step 4.

- [ ] **Step 4: Update HANDOFF.md (опционально, в конце)**

Добавить в `docs/HANDOFF.md` секцию про переезд чата: `/chat` убран, чат в правой панели WorkspaceLayout, AIAssistantPanel — dead code (для Подсистемы B). Обновить frontend-тесты 9→11.

---

## Self-Review (выполнено ассистентом после написания)

**1. Spec coverage:**
- ✅ Создать ChatPanel.vue → Task 1
- ✅ WorkspaceLayout: AI → Chat, FAB, isStaff gate → Task 2
- ✅ Убрать /chat из роутера + редиректы → Task 4
- ✅ Убрать пункт «Чат» из sidebar → Task 3
- ✅ Удалить ChatView.vue → Task 5
- ✅ usernameOptions minUsers:2 → Task 1 (в ChatPanel)
- ✅ Frontend тесты (mount + close) → Task 6
- ✅ Финальный прогон + ручной smoke → Task 7
- ✅ Деплой (push + build, без backend) → Task 8
- ✅ AIAssistantPanel НЕ удаляется → подтверждено (не упоминается в deletion steps)
- ✅ VAC в 360px эмпирическая проверка → Task 7 Step 4 пункт 10

**2. Placeholder scan:** TODO/TBD/«add error handling» — нет. Все шаги содержат полный код или точные команды. ✅

**3. Type consistency:**
- `ChatPanel` emits `close: []` → WorkspaceLayout `@close="closeChat"` — совпадает. ✅
- `defineEmits<{ close: [] }>()` в Task 1 ↔ тест `wrapper.emitted('close')` в Task 6 — совпадает. ✅
- `isStaff` computed в Task 2 → `v-if="isStaff"` — совпадает. ✅
- `usernameOptions = { minUsers: 2, currentUser: false }` → `:username-options="usernameOptions"` в template — совпадает. ✅

Всё консистентно.

**4. Риски отмечены:**
- `@vue/test-utils` может быть не установлен → Step 2 в Task 6 с инструкцией установить.
- VAC в 360px — эмпирический шаг в smoke.
- Удаление ChatView — с grep-проверкой перед rm.
- AIAssistantPanel — dead code, НЕ удаляется.

---

*План написан после отдыха. 💕 Канарейка жива, scope узкий (только A), TDD соблюдён.*
