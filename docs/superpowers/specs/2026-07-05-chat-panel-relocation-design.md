# CRM: Переезд чата в правую панель (Подсистема A) — Design

**Дата:** 2026-07-05
**Статус:** Approved (пользователь одобрил дизайн 2026-07-05)
**Автор совместной сессии:** пользователь + ассистент
**Связанные документы:** `2026-07-04-chat-messaging-design.md` (Подсистема I), `2026-07-04-chat-reply-design.md` (reply), `2026-07-04-chat-attachments-design.md` (файлы — заморожено)

## Контекст и проблема

Сейчас в CRM **два разных места** для коммуникации, и это путает:

1. **`/admin/chat`** (и `/manager/chat`, `/employee/chat`) — отдельная полноэкранная страница с `vue-advanced-chat`, чат с коллегами. Надо зайти через sidebar, покинуть текущий экран.
2. **AI-панель справа** в `WorkspaceLayout.vue` — узкий `aside w-[360px]`, `AIAssistantPanel.vue`, открывается FAB-кнопкой «AI». Изолирована от командного чата.

Пользователь хочет: **единую панель коммуникации справа** на месте AI-панели. Чат с коллегами переезжает туда, `/chat`-страницы убираются. Чат виден на всех страницах workspace (как раньше AI), сворачивается/разворачивается. Это первая из трёх подсистем большого трека «объединить чат с коллегами и AI».

### Декомпозиция большого трека (важно)

Запрос «чат с коллегами + AI в одном месте + уведомления со звуком» распадается на **три подсистемы**, каждая со своей спекой. Пытаться впихнуть всё в один план — путь к хаосу.

| # | Подсистема | Что | Спека |
|---|---|---|---|
| **A** | **Переезд чата в правую панель** (этот документ) — `/chat` убирается, чат встраивается в `WorkspaceLayout` вместо AI-панели | **этот документ** |
| **B** | **AI как канал** — новый канал «AI ассистент», сообщение туда → backend зовёт GLM → ответ как сообщение от AI-юзера | отдельная спека позже |
| **C** | **Уведомления со звуком** — WS push + звук + визуал при новом сообщении, даже если панель закрыта | отдельная спека позже |

Порядок: **A → B → C**. Эта спека описывает **только Подсистему A**.

### Что в дизайн НЕ входит (явный YAGNI для этой фазы)

- **AI-канал** → Подсистема B. Здесь AI-панель просто убирается из рендера (не удаляется файл — может пригодиться для B).
- **Звуковые уведомления** → Подсистема C. Здесь только визуальный unread-бейдж (как уже есть).
- **Файловые вложения в чат** → заморожено (была спека `2026-07-04-chat-attachments-design.md`, отложено до отдельной сессии).
- **Полная переработка AIAssistantPanel** → файл оставлен, не удаляется.
- **Сохранение черновика** при сворачивании панели → YAGNI.
- **Mobile-адаптив панели** (на весь экран <768px) → отдельная задача; тут только «не сломать».

---

## Решения (из brainstorming с пользователем)

1. **AI живёт как отдельный канал** в едином чате — но это Подсистема B. Здесь просто готовим место: убираем отдельную AI-панель, чат переезжает на её место.
2. **Звук + визуал везде** — Подсистема C. Здесь без звука, только визуал.
3. **Полный отказ от `/admin/chat`** как страницы. Чат встраивается в `WorkspaceLayout` на место `AIAssistantPanel`, виден на всех страницах workspace.

---

## Архитектура

### Сейчас

```
WorkspaceLayout.vue:
  [AppSidebar]  [main: <RouterView/>]  [AIAssistantPanel v-show="isAiOpen"]  (aside w-[360px])
  [FAB "AI" v-if="dashboard"]  (fixed right-4 bottom-4 z-40)

Router:
  /admin/chat      → ChatView.vue  (полноэкранный vue-advanced-chat)
  /manager/chat    → ChatView.vue
  /employee/chat   → ChatView.vue
```

### Станет

```
WorkspaceLayout.vue:
  [AppSidebar]  [main: <RouterView/>]  [ChatPanel v-show="chatOpen"]  (aside w-[360px])
  [FAB "Чат" v-if="showChatFab"]  (fixed right-4 bottom-4 z-40)

Router:
  /admin/chat      → redirect /admin/dashboard  (или просто убрано)
  /manager/chat    → redirect /manager/dashboard
  /employee/chat   → redirect /employee/dashboard
```

Чат становится **вездесущим** — как раньше AI. Пользователь не уходит со своей страницы, чтобы обсудить что-то с командой.

---

## Frontend изменения

### 1. Новый компонент `src/components/chat/ChatPanel.vue`

Обёртка над `vue-advanced-chat`, адаптированная под узкую панель. Содержит логику, перенесённую из `ChatView.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useChatSocket } from '@/composables/useChatSocket'
import { chatApi } from '@/api/chat'
import { toRoom, toMessage } from '@/composables/useChatAdapter'
import CreateChannelModal from '@/components/chat/CreateChannelModal.vue'

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

// Имя отправителя видно при ≥2 участников (вместо дефолта VAC ≥3)
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

// onSend / onFetch / onReply / openCreateModal / onChannelCreated —
// переносятся из ChatView.vue без изменений.
function onSend(event: any) {
  const { content, roomId, replyMessage } = event.detail[0]
  const replyToId = replyMessage?._id ? Number(replyMessage._id) : undefined
  store.sendMessage(Number(roomId), content, replyToId)
}
function onReply(_event: any) {}
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
function openCreateModal() { showCreateModal.value = true }
async function onChannelCreated() {
  showCreateModal.value = false
  await store.loadChannels()
  await store.loadUnread()
}
</script>

<template>
  <aside class="flex flex-col h-full bg-slate-50 border-l border-slate-200 shrink-0 w-[360px]">
    <header class="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-white">
      <div class="flex items-center gap-2">
        <h3 class="font-semibold text-sm">Чат команды</h3>
      </div>
      <button class="btn-ghost !p-1" title="Закрыть" @click="emit('close')">
        <!-- lucide X icon -->
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
    <CreateChannelModal v-if="showCreateModal" @close="showCreateModal = false" @created="onChannelCreated" />
  </aside>
</template>
```

### 2. `src/layouts/WorkspaceLayout.vue` — замена AI на чат

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

// Чат-панель доступна всем staff (не клиентам).
const isStaff = computed(() => auth.role && auth.role !== 'client')

// FAB-кнопка видна на дашбордах (как раньше AI), только для staff.
const showChatFab = computed(() => isStaff.value && route.path.endsWith('/dashboard'))

function openChat() { chatOpen.value = true }
function closeChat() { chatOpen.value = false }
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

**Изменения vs текущего WorkspaceLayout:**
- `AIAssistantPanel` → `ChatPanel`
- `isAiOpen` → `chatOpen`
- `openAi/closeAi` → `openChat/closeChat`
- FAB «AI ✨» → FAB «Чат»
- Добавлен `isStaff` gate (клиенты чат не видят)
- Логика `showChatFab` — на дашбордах (как раньше AI, договорённость из Bug 1)

### 3. `src/router/index.ts` — убрать `/chat` страницы

В children admin/manager/employee убрать строки:
```typescript
{ path: 'chat', component: () => import('@/views/ChatView.vue') },
```

Добавить редиректы (мягче для bookmark'ов):
```typescript
// В каждом layout-блоке (admin/manager/employee) на уровне children:
{ path: 'chat', redirect: (to) => to.path.replace('/chat', '/dashboard') },
```
(или просто `{ path: 'chat', redirect: './dashboard' }` — относительный redirect внутри layout.)

### 4. `src/components/sidebar/AppSidebar.vue` — убрать пункт «Чат»

Если в sidebar есть ссылка на `/chat` — убрать (чат теперь всегда справа, не через меню). Проверить и удалить.

### 5. `src/views/ChatView.vue` — удалить

Логика перенесена в `ChatPanel.vue`. Файл `ChatView.vue` становится мёртвым (после убирания из роутера его никто не импортирует). Удалить.

### 6. `src/components/ai/AIAssistantPanel.vue` — оставить, но не рендерить

Файл НЕ удаляется (может пригодиться для Подсистемы B — AI-канал). Просто перестаёт импортироваться в `WorkspaceLayout`. Если в других местах импортируется — проверить.

---

## Адаптация vue-advanced-chat под узкую панель

Панель `w-[360px]` — меньше, чем полноэкранный чат. У `vue-advanced-chat` двухколоночный layout (rooms list + messages), который в 360px не помещается рядом.

**Поведение VAC в узком контейнере (без доп. настройки):**
- При ширине контейнера < некоторого порога VAC автоматически скрывает rooms-list, показывая только активную комнату.
- Кнопка «назад к каналам» появляется в header активной комнаты.

**Риск:** порог авто-скрытия может не сработать на 360px. Тогда rooms-list и messages поделят ~180px каждый — некрасиво.

**Решение (если понадобится):** CSS-override через `::part()` (VAC — web-component,暴露 parts) или media-query внутри контейнера. Но сначала проверить дефолтное поведение на проде — возможно, ничего делать не надо.

**Эта часть — эмпирическая**, фиксится по факту визуального smoke. В план заложить шаг «проверить VAC в 360px, при необходимости добавить CSS-override».

---

## Что НЕ меняем (YAGNI)

- **Backend чат-API** — не трогаем вообще. Все endpoints, WS, store работают как есть.
- **БД / миграции** — нет.
- **`useChatSocket`, `useChatAdapter`, `stores/chat`** — без изменений (логика переезжает в ChatPanel как есть).
- **AI-логика** — не трогаем (Подсистема B).
- **Звук** — не добавляем (Подсистема C).

---

## Edge cases

| Случай | Поведение |
|---|---|
| Чат открыт + юзер переходит на другую страницу | `chatOpen` в `WorkspaceLayout` сохраняется, панель остаётся открытой. WS переconнектится через `useChatSocket`. |
| Закрыл панель посреди набора | Текст input теряется. YAGNI сохранять черновик. |
| Mobile (<768px) | Панель может вылезти за экран. Mobile-адаптив — отдельная задача. Тут только «не сломать»: `w-[360px]` на мобильном будет узким, но рабочим. |
| Пользователь с role=client | `isStaff` gate: ChatPanel не рендерится, FAB не показывается. Клиенты чат не видят (как сейчас). |
| WS reconnect при смене страницы | `useChatSocket` уже это умеет (проверено в чат-Подсистеме I). |
| Bookmark на `/admin/chat` | Редирект на `/admin/dashboard`. Пользователь увидит FAB «Чат». |
| VAC не помещается в 360px | Эмпирически проверить; при необходимости CSS-override (см. секцию адаптации). |

---

## Тестирование

### Backend
**Без изменений.** Чат-API не трогаем. Существующие 174 теста остаются зелёными.

### Frontend (vitest)

| # | Тест | Что проверяет |
|---|---|---|
| 1 | `ChatPanel монтируется с vue-advanced-chat` | компонент рендерится без ошибок |
| 2 | `ChatPanel emits close при клике на X` | кнопка закрытия работает |
| 3 | `WorkspaceLayout не рендерит ChatPanel для client` | isStaff gate |
| 4 | `WorkspaceLayout рендерит ChatPanel для manager` | isStaff gate |

### Ручной smoke (выполняет пользователь)
1. Открыть `/admin/dashboard` → справа FAB «Чат»
2. Кликнуть FAB → открывается панель чата (w-[360px])
3. Каналы видны, активный канал открывается, сообщения отправляются
4. Перейти на `/admin/proposals` → панель остаётся открытой
5. Свернуть (X) → панель закрывается, снова FAB
6. `/admin/chat` в URL → редирект на `/admin/dashboard`
7. VAC в 360px читаем (если нет — отметить для CSS-override)

---

## Деплой

- **Backup БД: НЕ нужен** (нет миграций, backend не меняется).
- Push → ssh pull → `npm run build` → готово. Backend не рестартуем (код не менялся).
- Smoke на проде: те же шаги что в «ручной smoke».

---

## Риски и компромиссы

- **VAC в 360px** — главный риск. Может понадобиться CSS-подгонка. Закладываем отдельный шаг в плане «проверить визуально, при необходимости override».
- **Удаление `/chat` страниц** — ломает bookmark'и. Смягчение: редирект на dashboard.
- **Удаление ChatView.vue** — если что-то ещё импортирует (кроме роутера), сломается. Перед удалением grep по импортам.
- **AIAssistantPanel остаётся мёртвым кодом** — осознанно (пригодится для B). Не удаляем.
- **Чат на каждой странице** — может отвлекать. Но это сознательный выбор пользователя (как раньше AI). FAB только на дашбордах смягчает.

---

## Порядок реализации (для плана)

1. Создать `ChatPanel.vue` (перенос логики из ChatView + `usernameOptions`).
2. Изменить `WorkspaceLayout.vue` (AI → Chat, FAB, isStaff gate).
3. Убрать `/chat` из роутера + добавить редиректы.
4. Убрать пункт «Чат» из sidebar.
5. Удалить `ChatView.vue` (после grep-проверки импортов).
6. Frontend тесты (4 теста).
7. Build + ручной smoke (визуальная проверка VAC в 360px).
8. Деплой (push + build, без backend).

---

*Спека написана перед сном. 💕 Завтра — план и реализация. Канарейка жива, YAGNI соблюдён, декомпозиция честная.*
