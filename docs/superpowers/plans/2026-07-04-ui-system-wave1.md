# UI System Wave 1 (BaseButton, BaseBadge, Toast, ConfirmModal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Создать фундамент UI-системы CRM: BaseButton, BaseBadge, Toast (vue-toastification), ConfirmModal — и мигрировать проблемные места (`alert()`/`prompt()`/удаление без подтверждения).

**Architecture:** 3 компонента в `src/components/ui/` (BaseButton через cva-стек уже установленный: class-variance-authority + clsx + tailwind-merge), Toast через плагин `vue-toastification@next` (темизация под brand-600), ConfirmModal + `useConfirm()` composable (Promise-based, singleton state). Глобальный `<ConfirmModal/>` монтируется один раз в `App.vue`. Старый мёртвый `components/ui/Button.vue` удаляется.

**Tech Stack:** Vue 3.5, TypeScript, Tailwind 3.4, cva (class-variance-authority), vue-toastification@next, @vueuse/core (onClickOutside).

**Спека:** `docs/superpowers/specs/2026-07-04-ui-system-wave1-design.md` (все решения и CSS-значения там).

**Тестирование:** Фронтенд-тест-инфраструктуры (Vitest) в проекте НЕТ. Поэтому:
- TDD применяется только где возможно без Vue-рендера: composable `useConfirm` (чистый TS, тестируется через `vitest` — ставим минимум для одного теста) ИЛИ проверяется вручную.
- Vue-компоненты — smoke-проверка через `npm run build` (vue-tsc валидирует типы) + ручная проверка в браузере.

---

## File Structure

| Файл | Ответственность | Статус |
|---|---|---|
| `package.json` | Добавить `vue-toastification@next` + `vitest` (devDep, для 1 теста useConfirm) | Modify |
| `src/main.ts` | Регистрация Toast плагина + импорт css | Modify |
| `src/App.vue` | Глобальный `<ConfirmModal/>` | Modify |
| `src/assets/main.css` | `.base-btn--*` и `.base-badge--*` классы в @layer components | Modify |
| `src/assets/toast-theme.css` | Override цветов vue-toastification под brand | Create |
| `src/plugins/toast.ts` | Реэкспорт `toast` с типизированным API | Create |
| `src/components/ui/BaseButton.vue` | Кнопка (cva), 5 variants | Create |
| `src/components/ui/BaseBadge.vue` | Бейдж (cva), 6 types | Create |
| `src/components/ui/ConfirmModal.vue` | Модалка подтверждения (a11y базовый) | Create |
| `src/composables/useConfirm.ts` | confirm({...}) → Promise<boolean> (singleton) | Create |
| `src/components/ui/Button.vue` | Мёртвый cva-код | **Delete** |
| `src/composables/useConfirm.test.ts` | Тест useConfirm (parallel resolve fix) | Create |
| Мигрируемые view | ProposalBuilder, NotesGrid, QuickAddBar, CallsView, ClientsView, TaskBoard | Modify |

---

## Task 1: Установить зависимости (vue-toastification + vitest)

**Files:**
- Modify: `package.json`, `package-lock.json`

- [ ] **Step 1: Установить vue-toastification (Vue 3 версия)**

```bash
npm install vue-toastification@next
```

Ожидание: пакет добавлен в `dependencies`. Версия для Vue 3 — `@next` tag (или `^2.0.0-rc`).

- [ ] **Step 2: Установить vitest (для теста useConfirm)**

```bash
npm install -D vitest
```

- [ ] **Step 3: Добавить test-скрипт в package.json**

В `package.json` → `scripts` добавить:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 4: Проверить сборку не сломалась**

Run: `npm run build`
Expected: build succeeds (vue-tsc не падает на новых типах vue-toastification).

- [ ] **Step 5: Коммит**

```bash
git add package.json package-lock.json
git commit -m "chore: add vue-toastification@next + vitest for UI system wave 1"
```

---

## Task 2: BaseButton.vue (cva)

**Files:**
- Create: `src/components/ui/BaseButton.vue`
- Modify: `src/assets/main.css` (CSS-классы)
- Delete: `src/components/ui/Button.vue` (мёртвый)

### Часть A: CSS-классы

- [ ] **Step 1: Добавить .base-btn классы в main.css**

В `src/assets/main.css`, в `@layer components` (после `.card`, строка 16), добавить:

```css
.base-btn { @apply inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed; }
.base-btn--primary { @apply bg-brand-600 text-white hover:bg-brand-700; }
.base-btn--secondary { @apply bg-white text-slate-600 border border-slate-300 hover:bg-slate-50; }
.base-btn--danger { @apply bg-red-600 text-white hover:bg-red-700; }
.base-btn--success { @apply bg-green-600 text-white hover:bg-green-700; }
.base-btn--ghost { @apply bg-transparent text-slate-500 hover:bg-slate-100; }
```

### Часть B: компонент

- [ ] **Step 2: Создать BaseButton.vue**

`src/components/ui/BaseButton.vue`:
```vue
<template>
  <button :class="classes" :disabled="disabled" :type="type">
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'success' | 'ghost'
  disabled?: boolean
  type?: 'button' | 'submit'
}>(), { variant: 'primary', disabled: false, type: 'button' })

const classes = computed(() => [
  'base-btn',
  `base-btn--${props.variant}`,
])
</script>
```

### Часть C: удалить мёртвый

- [ ] **Step 3: Проверить что старый Button.vue нигде не импортируется**

Run: `grep -rn "components/ui/Button" src/ --include='*.vue' --include='*.ts'`
Expected: 0 совпадений (разведка подтвердила — нигде не используется).

Если есть совпадения — НЕ удалять, а заменить импорты на BaseButton. Если 0 — удаляем.

- [ ] **Step 4: Удалить старый Button.vue**

```bash
rm src/components/ui/Button.vue
```

- [ ] **Step 5: Smoke-проверка сборки**

Run: `npm run build`
Expected: success.

- [ ] **Step 6: Коммит**

```bash
git add src/components/ui/BaseButton.vue src/components/ui/Button.vue src/assets/main.css
git commit -m "feat(ui): BaseButton component (5 variants), remove dead Button.vue"
```

---

## Task 3: BaseBadge.vue

**Files:**
- Create: `src/components/ui/BaseBadge.vue`
- Modify: `src/assets/main.css`

- [ ] **Step 1: Добавить .base-badge классы в main.css**

В `src/assets/main.css`, в `@layer components`, после `.base-btn--ghost`:

```css
.base-badge { @apply inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-semibold; }
.base-badge--success { @apply bg-green-600 text-white; }
.base-badge--warning { @apply bg-amber-600 text-slate-900; }
.base-badge--danger { @apply bg-red-600 text-white; }
.base-badge--info { @apply bg-blue-600 text-white; }
.base-badge--purple { @apply bg-purple-600 text-white; }
.base-badge--gray { @apply bg-slate-600 text-white; }
```

(Контраст WCAG AA проверен в спеке: warning — тёмный текст на amber-600, gray — slate-600 с белым.)

- [ ] **Step 2: Создать BaseBadge.vue**

`src/components/ui/BaseBadge.vue`:
```vue
<template>
  <span :class="classes"><slot /></span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  type?: 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'gray'
}>(), { type: 'gray' })

const classes = computed(() => [
  'base-badge',
  `base-badge--${props.type}`,
])
</script>
```

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Коммит**

```bash
git add src/components/ui/BaseBadge.vue src/assets/main.css
git commit -m "feat(ui): BaseBadge component (6 types, WCAG AA contrast)"
```

---

## Task 4: Toast plugin + регистрация

**Files:**
- Create: `src/plugins/toast.ts`
- Create: `src/assets/toast-theme.css`
- Modify: `src/main.ts`

- [ ] **Step 1: Создать toast-theme.css (override под бренд)**

`src/assets/toast-theme.css`:
```css
/* Override vue-toastification default colors to match CRM palette.
   Border-left 4px = type color (как в мокапе визуального брейншторма). */

.Vue-Toastification__toast--success {
  background-color: #16a34a !important;
  border-left: 4px solid #15803d !important;
}
.Vue-Toastification__toast--error {
  background-color: #dc2626 !important;
  border-left: 4px solid #b91c1c !important;
}
.Vue-Toastification__toast--info {
  background-color: #2563eb !important;
  border-left: 4px solid #1d4ed8 !important;
}
.Vue-Toastification__toast--warning {
  background-color: #d97706 !important;
  color: #0f172a !important;
  border-left: 4px solid #b45309 !important;
}
.Vue-Toastification__toast--warning .Vue-Toastification__toast-body,
.Vue-Toastification__toast--warning .Vue-Toastification__close-button {
  color: #0f172a !important;
}
/* Контейнер: правый верхний угол, поверх всего */
.Vue-Toastification__container.top-right {
  z-index: 9999 !important;
}
```

- [ ] **Step 2: Создать plugins/toast.ts**

`src/plugins/toast.ts`:
```ts
import { toast as vToast } from 'vue-toastification'
import type { POSITION } from 'vue-toastification'

// Реэкспорт с типизированным API. Конфиг регистрируется в main.ts.
export const toast = {
  success: (msg: string) => vToast.success(msg),
  error: (msg: string) => vToast.error(msg),
  info: (msg: string) => vToast.info(msg),
  warning: (msg: string) => vToast.warning(msg),
}

export { vToast, POSITION }
```

- [ ] **Step 3: Зарегистрировать Toast в main.ts**

Заменить содержимое `src/main.ts`:
```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import { POSITION } from 'vue-toastification'
import 'vue-toastification/dist/index.css'
import { router } from './router'
import App from './App.vue'
import './assets/main.css'
import './assets/toast-theme.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

app.use(Toast, {
  position: POSITION.TOP_RIGHT,
  timeout: 4000,
  closeOnClick: true,
  pauseOnHover: true,
  newestOnTop: true,
  maxToasts: 5,
})

app.mount('#app')
```

- [ ] **Step 4: Smoke-проверка**

Run: `npm run build`
Expected: success. Если падает на `POSITION` — проверить, что `vue-toastification@next` установлен (Task 1).

- [ ] **Step 5: Коммит**

```bash
git add src/plugins/toast.ts src/assets/toast-theme.css src/main.ts
git commit -m "feat(ui): Toast plugin (vue-toastification) with brand-themed colors, top-right"
```

---

## Task 5: useConfirm composable + тест

**Files:**
- Create: `src/composables/useConfirm.ts`
- Create: `src/composables/useConfirm.test.ts`
- Create: `vitest.config.ts` (минимум)

- [ ] **Step 1: Создать vitest.config.ts**

`vitest.config.ts` (корень проекта):
```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})
```

- [ ] **Step 2: Написать тест (RED)**

`src/composables/useConfirm.test.ts`:
```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { nextTick } from 'vue'

// Импорт после создания useConfirm.ts (Step 4). До этого — RED.
import { useConfirm } from './useConfirm'

describe('useConfirm', () => {
  it('confirm() returns a promise that resolves true on resolve(true)', async () => {
    const { confirm, resolve, visible } = useConfirm()
    const p = confirm({ title: 'Test?' })
    expect(visible.value).toBe(true)
    resolve(true)
    expect(await p).toBe(true)
    expect(visible.value).toBe(false)
  })

  it('confirm() resolves false on resolve(false) (cancel)', async () => {
    const { confirm, resolve } = useConfirm()
    const p = confirm({ title: 'Test?' })
    resolve(false)
    expect(await p).toBe(false)
  })

  it('parallel confirm() resolves previous as false (no hung promise)', async () => {
    const { confirm, resolve, visible } = useConfirm()
    const p1 = confirm({ title: 'First?' })
    const p2 = confirm({ title: 'Second?' })
    // p1 should resolve false (cancelled) when p2 opens
    expect(await p1).toBe(false)
    expect(visible.value).toBe(true)
    resolve(true)
    expect(await p2).toBe(true)
  })
})
```

- [ ] **Step 3: Прогнать тест — должен упасть (модуль не существует)**

Run: `npx vitest run src/composables/useConfirm.test.ts`
Expected: FAIL — `Cannot find module './useConfirm'`.

- [ ] **Step 4: Создать useConfirm.ts (GREEN)**

`src/composables/useConfirm.ts`:
```ts
import { ref } from 'vue'

export interface ConfirmOptions {
  title: string
  message?: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

const visible = ref(false)
const options = ref<ConfirmOptions>({ title: '' })
let resolver: ((v: boolean) => void) | null = null

export function useConfirm() {
  function confirm(opts: ConfirmOptions): Promise<boolean> {
    // Если уже есть открытый confirm — резолвим предыдущий как false (отмена),
    // иначе первый await зависнет навсегда при параллельном вызове.
    if (visible.value && resolver) {
      resolver(false)
      resolver = null
    }
    options.value = opts
    visible.value = true
    return new Promise<boolean>((resolve) => { resolver = resolve })
  }

  function resolve(value: boolean) {
    visible.value = false
    resolver?.(value)
    resolver = null
  }

  return { visible, options, confirm, resolve }
}
```

- [ ] **Step 5: Прогнать тест — должен пройти**

Run: `npx vitest run src/composables/useConfirm.test.ts`
Expected: 3 passed.

- [ ] **Step 6: Коммит**

```bash
git add src/composables/useConfirm.ts src/composables/useConfirm.test.ts vitest.config.ts
git commit -m "feat(ui): useConfirm composable (Promise-based, parallel-call safe) + tests"
```

---

## Task 6: ConfirmModal.vue + монтирование в App.vue

**Files:**
- Create: `src/components/ui/ConfirmModal.vue`
- Modify: `src/App.vue`

- [ ] **Step 1: Создать ConfirmModal.vue**

`src/components/ui/ConfirmModal.vue`:
```vue
<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-[10000] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      @click.self="cancel"
      @keydown.esc="cancel"
    >
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div
        ref="cardRef"
        tabindex="-1"
        class="relative bg-white rounded-xl shadow-2xl border border-slate-200 max-w-md w-full p-6 z-10"
      >
        <h3 :id="titleId" class="font-bold text-base text-slate-900">
          {{ options.title }}
        </h3>
        <p v-if="options.message" class="text-sm text-slate-500 mt-2">
          {{ options.message }}
        </p>
        <div class="flex gap-2 justify-end mt-5">
          <BaseButton variant="secondary" @click="cancel">
            {{ options.cancelText || 'Отмена' }}
          </BaseButton>
          <BaseButton
            :variant="options.danger ? 'danger' : 'primary'"
            ref="confirmBtnRef"
            @click="ok"
          >
            {{ options.confirmText || 'Подтвердить' }}
          </BaseButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, useId } from 'vue'
import { onClickOutside } from '@vueuse/core'
import BaseButton from './BaseButton.vue'
import { useConfirm } from '@/composables/useConfirm'

const { visible, options, resolve } = useConfirm()
const cardRef = ref<HTMLElement | null>(null)
const confirmBtnRef = ref<InstanceType<typeof BaseButton> | null>(null)
const titleId = useId?.() ?? 'confirm-modal-title'

// Внешний клик по карточке = cancel (onClickOutside из @vueuse/core)
onClickOutside(cardRef, () => cancel())

// При открытии — переводим фокус на кнопку подтверждения (a11y)
watch(visible, async (v) => {
  if (v) {
    await nextTick()
    // confirmBtnRef указывает на BaseButton; достаём нативный <button>
    const el = (confirmBtnRef.value as any)?.$el as HTMLElement | undefined
    el?.focus()
  }
})

function ok() { resolve(true) }
function cancel() { resolve(false) }
</script>
```

(Примечание: `useId` доступен в Vue 3.5+. Если `useId` не определён — fallback на константу `'confirm-modal-title'`. `onClickOutside` из @vueuse/core уже установлен.)

- [ ] **Step 2: Смонтировать ConfirmModal в App.vue**

Заменить содержимое `src/App.vue`:
```vue
<script setup lang="ts">
import { RouterView } from 'vue-router'
import ConfirmModal from '@/components/ui/ConfirmModal.vue'
</script>

<template>
  <RouterView />
  <ConfirmModal />
</template>
```

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Ручная проверка в браузере (dev server)**

Run: `npm run dev` → открыть http://localhost:5173
В консоли браузера (временно, для проверки):
```js
// Этот код выполняется в DevTools консоли, не в плане
// (просто для smoke-теста; в реальном коде используем useConfirm)
```
Альтернатива — пропустить ручную проверку до миграции (Task 7+, где useConfirm реально вызывается).

- [ ] **Step 5: Коммит**

```bash
git add src/components/ui/ConfirmModal.vue src/App.vue
git commit -m "feat(ui): ConfirmModal with a11y (role/aria/focus/esc/click-outside), mounted globally"
```

---

## Task 7: Миграция ProposalBuilder — alert() → toast

**Files:**
- Modify: `src/components/proposals/ProposalBuilder.vue`

- [ ] **Step 1: Прочитать файл и найти alert()**

Run: `grep -n "alert(" src/components/proposals/ProposalBuilder.vue`
Expected: строки 156, 214, 221, 224.

- [ ] **Step 2: Импортировать toast и заменить alert() на toast.error()**

В `<script setup>` ProposalBuilder.vue добавить импорт:
```ts
import { toast } from '@/plugins/toast'
```

Заменить каждое `alert(...)`:
- Строка 156: `alert('Сначала создайте КП')` → `toast.warning('Сначала создайте КП')`
- Строка 214: `alert(st.error || 'Ошибка генерации PDF')` → `toast.error(st.error || 'Ошибка генерации PDF')`
- Строка 221: `alert('PDF не успел подготовиться за 15 секунд. Попробуйте ещё раз.')` → `toast.error('PDF не успел подготовиться за 15 секунд. Попробуйте ещё раз.')`
- Строка 224: `alert(msg)` → `toast.error(msg)`

- [ ] **Step 3: Добавить toast.success на успешное сохранение**

Найти место успешного сохранения КП (после `await proposalsApi.create(...)` или `update`) и добавить:
```ts
toast.success('КП сохранено')
```
(Если такого места нет — пропустить; цель — показать success-toast хотя бы на одном действии.)

- [ ] **Step 4: Smoke-проверка**

Run: `npm run build`
Expected: success. + `grep -c "alert(" src/components/proposals/ProposalBuilder.vue` → 0.

- [ ] **Step 5: Коммит**

```bash
git add src/components/proposals/ProposalBuilder.vue
git commit -m "refactor(proposals): replace alert() with toast in ProposalBuilder"
```

---

## Task 8: Миграция NotesGrid — prompt() → модалка

**Files:**
- Modify: `src/components/workspace/NotesGrid.vue`

- [ ] **Step 1: Прочитать NotesGrid.vue, найти prompt()**

Run: `grep -n "prompt(\|alert(" src/components/workspace/NotesGrid.vue`
Expected: строка 15 (`prompt('Заголовок заметки?')`).

- [ ] **Step 2: Заменить prompt() на нативную модалку с textarea**

Так как в волне 1 у нас есть ConfirmModal (но он без поля ввода — только title/message/2 кнопки), для создания заметки с **полем ввода** нужен простой inline-компонент или локальная модалка в NotesGrid.

Минимальное решение (без нового компонента): использовать `<dialog>` или локальный `v-if` блок с textarea. Прочитать NotesGrid.vue целиком, понять структуру, заменить `prompt()` на локальную модалку:

```vue
<!-- в <script setup>: -->
const showNoteModal = ref(false)
const newNoteTitle = ref('')
function openNoteModal() {
  newNoteTitle.value = ''
  showNoteModal.value = true
}
async function createNote() {
  if (!newNoteTitle.value.trim()) return
  // ... логика создания (как было после prompt)
  showNoteModal.value = false
  toast.success('Заметка создана')
}
```

```vue
<!-- в <template>, добавить модалку (по образцу ConfirmModal): -->
<Teleport to="body">
  <div v-if="showNoteModal" class="fixed inset-0 z-[10000] flex items-center justify-center p-4" @click.self="showNoteModal = false">
    <div class="absolute inset-0 bg-black/50" />
    <div class="relative bg-white rounded-xl shadow-2xl p-6 max-w-md w-full z-10">
      <h3 class="font-bold text-base mb-3">Новая заметка</h3>
      <input v-model="newNoteTitle" class="input mb-4" placeholder="Заголовок заметки" @keydown.enter="createNote" autofocus />
      <div class="flex gap-2 justify-end">
        <BaseButton variant="secondary" @click="showNoteModal = false">Отмена</BaseButton>
        <BaseButton variant="primary" @click="createNote">Создать</BaseButton>
      </div>
    </div>
  </div>
</Teleport>
```

(Импортировать `BaseButton` и `toast` в NotesGrid.)

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build && grep -c "prompt(" src/components/workspace/NotesGrid.vue`
Expected: success + 0 prompt().

- [ ] **Step 4: Коммит**

```bash
git add src/components/workspace/NotesGrid.vue
git commit -m "refactor(notes): replace prompt() with inline modal for note creation"
```

---

## Task 9: Миграция QuickAddBar — prompt() → модалка

**Files:**
- Modify: `src/components/workspace/QuickAddBar.vue`

- [ ] **Step 1: Прочитать QuickAddBar.vue, найти prompt()**

Строки 22 (выбор исполнителя), 38 (тип срока), 45 (значение срока). Это сложнее — `prompt()` используется как пошаговый wizard (исполнитель → тип → значение).

- [ ] **Step 2: Заменить wizard-prompt() на единую модалку создания задачи**

Создать локальную модалку с 3 полями: исполнитель (select), тип срока (radio: часы/дни), значение (number). Один `<BaseButton>` «Создать». Логика та же, что в оригинале, но в одном окне вместо 3 prompt'ов.

Прочитать QuickAddBar.vue,重构ировать `addTask()`:
```ts
const showTaskModal = ref(false)
const taskForm = ref({ assigneeId: 0 as number, durationType: 'hours' as 'hours'|'days', durationValue: 1 })

function openTaskModal() {
  taskForm.value = { assigneeId: 0, durationType: 'hours', durationValue: 1 }
  showTaskModal.value = true
}
async function createTask() {
  // ...логика из оригинала, используя taskForm.value вместо prompt-ответов
  showTaskModal.value = false
  toast.success('Задача создана')
}
```

(Модалка по образцу Task 8, но с select/radio/number.)

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build && grep -c "prompt(" src/components/workspace/QuickAddBar.vue`
Expected: success + 0 prompt().

- [ ] **Step 4: Коммит**

```bash
git add src/components/workspace/QuickAddBar.vue
git commit -m "refactor(tasks): replace 3-step prompt() wizard with single task-creation modal"
```

---

## Task 10: Миграция CallsView (manager) — prompt() → модалка

**Files:**
- Modify: `src/views/manager/CallsView.vue`

- [ ] **Step 1: Прочитать, найти prompt()**

Строки 105 (название задачи), 125 (заголовок заметки), 129 (текст заметки).

- [ ] **Step 2: Заменить prompt() на локальные модалки**

Аналогично Task 8/9 — локальные модалки с input/textarea. Для задачи — input названия; для заметки — input заголовка + textarea текста.

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build && grep -c "prompt(" src/views/manager/CallsView.vue`
Expected: success + 0 prompt().

- [ ] **Step 4: Коммит**

```bash
git add src/views/manager/CallsView.vue
git commit -m "refactor(calls): replace prompt() with modals for task/note creation"
```

---

## Task 11: Миграция TaskBoard + CallsView — мёртвые btn-классы → BaseButton

**Files:**
- Modify: `src/components/workspace/TaskBoard.vue`
- Modify: `src/views/manager/CallsView.vue`

- [ ] **Step 1: Найти мёртвые btn-классы**

Run: `grep -rn "btn-success\|btn-danger\|btn-secondary" src/`
Expected: совпадения в TaskBoard.vue и/или CallsView.vue.

- [ ] **Step 2: В TaskBoard.vue заменить на BaseButton**

Импортировать `BaseButton`, заменить `<button class="btn-success">` → `<BaseButton variant="success">`, `btn-danger` → `variant="danger"`, `btn-secondary` → `variant="secondary"`.

- [ ] **Step 3: В CallsView.vue заменить btn-secondary**

Аналогично.

- [ ] **Step 4: Smoke-проверка**

Run: `npm run build && grep -rn "btn-success\|btn-danger\|btn-secondary" src/`
Expected: success + 0 совпадений (все мёртвые классы устранены).

- [ ] **Step 5: Коммит**

```bash
git add src/components/workspace/TaskBoard.vue src/views/manager/CallsView.vue
git commit -m "refactor(ui): replace dead btn-* classes with BaseButton in TaskBoard/CallsView"
```

---

## Task 12: Confirm на удаление — ClientsView

**Files:**
- Modify: `src/views/admin/ClientsView.vue`

- [ ] **Step 1: Прочитать, найти удаление клиента без подтверждения**

Найти `deleteClient(id)` или аналог, который вызывается сразу (без window.confirm).

- [ ] **Step 2: Обернуть в useConfirm**

```ts
import { useConfirm } from '@/composables/useConfirm'
import { toast } from '@/plugins/toast'
const { confirm } = useConfirm()

async function removeClient(id: number, name: string) {
  const ok = await confirm({
    title: 'Удалить клиента?',
    message: `Клиент «${name}» будет удалён. Действие нельзя отменить. Связанные КП останутся.`,
    confirmText: 'Удалить',
    danger: true,
  })
  if (!ok) return
  await clientsApi.delete(id)
  toast.success('Клиент удалён')
  await store.load()
}
```

Привязать `@click="removeClient(c.id, c.name)"` в шаблоне.

- [ ] **Step 3: Smoke-проверка**

Run: `npm run build`
Expected: success.

- [ ] **Step 4: Коммит**

```bash
git add src/views/admin/ClientsView.vue
git commit -m "feat(clients): confirm modal before client deletion"
```

---

## Task 13: Финальная проверка + деплой

**Files:** — (операционный)

- [ ] **Step 1: Полный набор тестов**

Run: `npm run test`
Expected: useConfirm тесты (3) pass.

- [ ] **Step 2: Сборка**

Run: `npm run build`
Expected: success, 0 TypeScript errors.

- [ ] **Step 3: Проверка что alert/prompt/мёртвые классы устранены**

Run:
```bash
grep -rn "alert(\|prompt(" src/ --include='*.vue' --include='*.ts' | grep -v "QuickActions\|placeholder\|//\|v-model\|import"
grep -rn "btn-success\|btn-danger\|btn-secondary" src/
```
Expected: 0 совпадений (или только QuickActions.vue где `prompt` — поле объекта AI, не window.prompt).

- [ ] **Step 4: Деплой dist/ на CRM**

```bash
# Локально (как делали раньше):
# 1. dist/ уже собран в Step 2
# 2. scp на сервер, замена целиком
scp -r -i ~/.ssh/kyk_server_key dist/* root@72.56.246.21:/var/www/crmks/dist/
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 "nginx -s reload"
```

- [ ] **Step 5: Ручная проверка на проде**

Открыть http://72.56.246.21 (или https://crmdot.ru если домен уже подключён):
- Login → войти admin'ом
- Proposals → создать КП → проверить toast.success
- Clients → попробовать удалить → должна появиться ConfirmModal
- Notes → создать заметку → модалка с input (не prompt)
- Tasks → кнопки должны иметь стили (BaseButton)
- Проверить toast.error (спровоцировать ошибку, например PDF на пустом КП)

- [ ] **Step 6: Merge в main + обновить HANDOFF**

```bash
git checkout main
git merge feat/ui-system-wave1 --no-ff -m "Merge UI system wave 1 (BaseButton, BaseBadge, Toast, ConfirmModal)"
git push origin main
# Обновить HANDOFF.md: отметить UI-систему как сделанную, волна 2 в очередь
```

---

## Self-Review (выполнено автором плана)

**1. Spec coverage:**
- BaseButton (5 variants) → Task 2. ✓
- BaseBadge (6 types, WCAG) → Task 3. ✓
- Toast (vue-toastification, top-right, 4 типа, темизация) → Task 4. ✓
- ConfirmModal + useConfirm (Promise, parallel-safe, a11y) → Tasks 5, 6. ✓
- Миграция alert() → toast → Task 7 (ProposalBuilder). ✓
- Миграция prompt() → модалки → Tasks 8 (NotesGrid), 9 (QuickAddBar), 10 (CallsView). ✓
- Мёртвые btn-классы → BaseButton → Task 11. ✓
- Confirm на удаление → Task 12 (ClientsView). ✓
- Деплой → Task 13. ✓
- Удаление старого Button.vue → Task 2 Step 4. ✓
- BaseBadge массово по view — явно НЕ в этой волне (волна 2). ✓

**2. Placeholder scan:** нет TBD/TODO; все CSS-значения конкретные; код в шагах — финальный (не псевдо). Единственное «прочитать файл и найти» (Tasks 7-12 Step 1) — это инструкции по разведке конкретных строк, после которых идёт конкретный код замены.

**3. Type consistency:**
- `useConfirm()` возвращает `{ visible, options, confirm, resolve }` — едино во всех задачах.
- `ConfirmOptions` интерфейс (title, message?, confirmText?, cancelText?, danger?) — консистентен в Task 5 (определение) и Task 12 (использование).
- BaseButton `variant` prop: `primary | secondary | danger | success | ghost` — едино в Task 2 (определение) и Tasks 6/11/12 (использование).
- BaseBadge `type` prop: `success | warning | danger | info | purple | gray` — едино.
- Toast API: `toast.success/error/info/warning(msg: string)` — едино.

**Риски (явно):**
- **Vitest + ESM:** vitest может потребовать `environment: 'jsdom'` если тесты используют Vue reactivity в браузерном контексте. В Task 5 использую `environment: 'node'` (useConfirm — чистый TS + Vue refs, работают в node). Если падает — переключить на jsdom + `npm i -D jsdom`.
- **useId в Vue 3.5:** `useId()` доступен с Vue 3.5+. Проект на Vue 3.5.35 — ОК. Если понизят — fallback на константу (уже в коде `?? 'confirm-modal-title'`).
- **Tasks 8-10 (prompt → модалки):** требуют чтения конкретного файла и адаптации логики wizard (особенно QuickAddBar с 3-step prompt). В плане дан образец модалки + инструкция; исполнитель читает реальный код и адаптирует. Это намеренно — точный код зависит от текущей структуры файла.
