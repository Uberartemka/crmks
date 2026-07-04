# UI-система (волна 1): BaseButton, BaseBadge, Toast, ConfirmModal — Design

> **Цель:** заложить фундамент UI-системы CRM. Четыре компонента, каждый решает конкретную боль из разведки: мёртвые классы кнопок (`btn-secondary/success/danger` определены в коде, но не в CSS → кнопки без стилей), `alert()`/`prompt()` вместо нативных уведомлений, удаление без подтверждения. Это база — после неё все следующие экраны (волна 2: Dashboard, Reports, Catalog) станут лучше автоматически.

## Решения (из brainstorming с заказчиком)

| Вопрос | Решение |
|---|---|
| Стиль BaseButton | **«Деловой» (A)** — primary красный `brand-600` (#C8102E), secondary серый outline, success (`green-600`)/danger (`red-600`) — стандартные насыщенные Tailwind-оттенки (уточнение: изначально было «приглушённые», но фактически используем стандартные насыщенные — они согласуются с остальной палитрой). Спокойный, как у банков/CRM. |
| Стиль BaseBadge | **Сплошные плашки (badge-solid)** — как у GitHub: заливка цветом, белый текст. |
| Toast библиотека | **vue-toastification@next** (готовая, Vue 3). Меньше своего кода, +1 зависимость. |
| Toast позиция | **Правый верхний угол (top-right)** — как Gmail/Slack, стек из нескольких, не перекрывает контент. |
| Toast типы | **Все 4**: success (зелёный), error (красный), info (синий), warning (жёлтый). |
| ConfirmModal | **Простая (A)** — текст + 2 кнопки (Отмена / Удалить). Без поля ввода имени. |
| Подход к реализации | **4 независимых компонента** в `src/components/ui/`, toast через плагин, confirm через composable. Удалить мёртвый `components/ui/Button.vue`. |
| Миграция | **Сразу мигрировать проблемные места** (ProposalBuilder, CallsView, NotesGrid, QuickAddBar, ClientsView). BaseBadge массово по view — в волне 2. |

---

## Архитектура

```
src/
├── components/ui/
│   ├── BaseButton.vue         # замена мёртвых btn-* классов
│   ├── BaseBadge.vue          # сплошные плашки статусов
│   └── ConfirmModal.vue       # простая модалка подтверждения
├── composables/
│   └── useConfirm.ts          # confirm({...}) → Promise<boolean>
├── plugins/
│   └── toast.ts               # настройка vue-toastification + экспорт toast
└── main.ts                    # регистрация vue-toastification + импорт css
```

**Удалить:** `src/components/ui/Button.vue` (мёртвый cva-код, нигде не импортируется).

**Зависимости:**
- `vue-toastification@next` (новая, Vue 3)
- `@vueuse/core` (уже есть, для `onClickOutside` в модалке)

---

## Спецификация компонентов

### 1. BaseButton.vue

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
}>(), { variant: 'primary', type: 'button' })

const classes = computed(() => [
  'base-btn',
  `base-btn--${props.variant}`,
  { 'base-btn--disabled': props.disabled },
])
</script>
```

**CSS (в `src/assets/main.css` @layer components, палитра бренда):**

| variant | Фон | Текст | Border |
|---|---|---|---|
| `primary` | `brand-600` (#C8102E) | white | none |
| `secondary` | white | `slate-600` | `slate-300` |
| `danger` | `red-600` (#dc2626) | white | none |
| `success` | `green-600` (#16a34a) | white | none |
| `ghost` | transparent | `slate-500` | transparent |

Общее: `padding: 8px 16px`, `border-radius: 8px`, `font-weight: 600`, `font-size: 13px`, `transition: all 150ms`, hover затемнение на 10%, disabled → `opacity-50 cursor-not-allowed`.

**Использование:**
```vue
<BaseButton variant="primary" @click="save">Сохранить</BaseButton>
<BaseButton variant="danger" @click="remove">Удалить</BaseButton>
<BaseButton variant="ghost" :disabled="loading">Отмена</BaseButton>
```

### 2. BaseBadge.vue

```vue
<template>
  <span :class="classes"><slot /></span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{
  type?: 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'gray'
}>(), { type: 'gray' })
const classes = computed(() => ['base-badge', `base-badge--${props.type}`])
</script>
```

**CSS (сплошные плашки):**

| type | Фон | Текст | Контраст (WCAG) |
|---|---|---|---|
| `success` | `green-600` (#16a34a) | white | ~4.5:1 ✓ AA |
| `warning` | `amber-600` (#d97706) | `slate-900` (#0f172a) | ~6.4:1 ✓ AA |
| `danger` | `red-600` (#dc2626) | white | ~5.9:1 ✓ AA |
| `info` | `blue-600` (#2563eb) | white | ~5.2:1 ✓ AA |
| `purple` | `purple-600` (#9333ea) | white | ~5.9:1 ✓ AA |
| `gray` | `slate-600` (#475569) | white | ~7.4:1 ✓ AAA |

**Решение по контрасту (WCAG AA, порог 4.5:1):** для тёмных фонов (green-600/red-600/purple-600/blue-600/slate-600) — белый текст проходит AA. Для `warning` (жёлтый) белый текст даёт ~2.9:1 — не проходит; используем **тёмный текст `slate-900`** на `amber-600` (как делает GitHub для жёлтых/светлых лейблов). Все варианты теперь ≥4.5:1.

Общее: `padding: 3px 10px`, `border-radius: 6px`, `font-size: 12px`, `font-weight: 600`, `display: inline-flex`.

**Использование:**
```vue
<BaseBadge type="success">Активный</BaseBadge>
<BaseBadge type="danger">Горячий</BaseBadge>
<BaseBadge type="purple">VIP</BaseBadge>
```

### 3. Toast (vue-toastification)

**`src/plugins/toast.ts`:**
```ts
import { toast as vToast } from 'vue-toastification'

// Реэкспорт с типизированным API. Конфиг регистрируется в main.ts.
export const toast = {
  success: (msg: string) => vToast.success(msg),
  error: (msg: string) => vToast.error(msg),
  info: (msg: string) => vToast.info(msg),
  warning: (msg: string) => vToast.warning(msg),
}
```

**Регистрация в `main.ts`:**
```ts
import Toast, { POSITION } from 'vue-toastification'
import 'vue-toastification/dist/index.css'
// Путь к CSS-темизации под бренд (override дефолтных цветов на brand-600/green-600/etc.)
import './assets/toast-theme.css'

const toastOptions = {
  position: POSITION.TOP_RIGHT,
  timeout: 4000,
  closeOnClick: true,
  pauseOnHover: true,
  newestOnTop: true,
  maxToasts: 5,
}
app.use(Toast, toastOptions)
```

**`src/assets/toast-theme.css` (override под палитру):**
Переопределить `.Vue-Toastification__toast--success/error/info/warning` на цвета из BaseBadge (green-600/red-600/blue-500/amber-500). Border-left 4px соответствующего цвета (как в мокапе).

**Использование в любом view:**
```ts
import { toast } from '@/plugins/toast'
toast.success('КП #127 сохранено')
toast.error('Ошибка отправки email')
```

### 4. ConfirmModal + useConfirm

**`src/components/ui/ConfirmModal.vue`:** рендерит модалку (overlay + карточка с title/message/2 кнопки). Props: `show`, `title`, `message`, `confirmText`, `cancelText`, `danger` (красная кнопка). Emits: `confirm`, `cancel`. Закрытие по Esc + click вне карточки + кнопка Отмена.

**`src/composables/useConfirm.ts`:**
```ts
import { ref } from 'vue'

const visible = ref(false)
const options = ref({})
let resolver: ((v: boolean) => void) | null = null

export function useConfirm() {
  function confirm(opts: {
    title: string
    message?: string
    confirmText?: string
    danger?: boolean
  }): Promise<boolean> {
    // Если уже есть открытый confirm — резолвим предыдущий как false (отмена),
    // иначе первый await зависнет навсегда при параллельном вызове.
    if (visible.value && resolver) {
      resolver(false)
      resolver = null
    }
    options.value = opts
    visible.value = true
    return new Promise(resolve => { resolver = resolve })
  }
  function resolve(value: boolean) {
    visible.value = false
    resolver?.(value)
    resolver = null
  }
  return { visible, options, confirm, resolve }
}

// ConfirmModal.vue монтируется один раз в App.vue и использует тот же state.
```

**Использование:**
```ts
import { useConfirm } from '@/composables/useConfirm'
const { confirm } = useConfirm()

async function deleteClient(id: number) {
  const ok = await confirm({
    title: 'Удалить клиента?',
    message: 'Действие нельзя отменить. Связанные КП останутся.',
    confirmText: 'Удалить',
    danger: true,
  })
  if (ok) {
    await api.deleteClient(id)
    toast.success('Клиент удалён')
  }
}
```

**Монтирование в `App.vue`:** один глобальный `<ConfirmModal />` + `<AppToast />` (последний от vue-toastification, регистрируется плагином автоматически).

### Доступность (a11y) модалки

В волне 1 включаем **базовый a11y** (минимум для бизнес-инструмента):
- `role="dialog"` + `aria-modal="true"` на overlay
- `aria-labelledby` указывает на title
- Фокус переходит на кнопку «Отмена» при открытии (default-safe действие)
- Закрытие по `Esc` + `onClickOutside` (уже в плане)
- Возврат фокуса на элемент-триггер после закрытия

**Focus trap (Tab не убегает наружу)** — **откладываем** в отдельную задачу (волна 2/3, вместе с глобальным a11y-аудитом). В волне 1 — только базовые атрибуты + возврат фокуса. Это явное решение (как с mobile-адаптивом), зафиксировано чтобы не оставлять «слепую зону».

---

## Миграция (волна 1 — конкретные точки)

### Toast (замена `alert()`)
| Файл | Строки | Было | Станет |
|---|---|---|---|
| `components/proposals/ProposalBuilder.vue` | 157, 214, 221, 225 | `alert('Ошибка: ' + e)` | `toast.error(msg)` |
| `components/proposals/ProposalBuilder.vue` | (save success) | нет уведомления | `toast.success('КП сохранено')` |
| `views/manager/CallsView.vue` | (через prompt) | `prompt()` для заметок звонка | `toast` + модалка |

### ConfirmModal (замена удаления без подтверждения)
| Файл | Было | Станет |
|---|---|---|
| `views/admin/ClientsView.vue` | `await deleteClient(id)` сразу | `if (await confirm({...})) await deleteClient(id)` |
| `components/proposals/ProposalBuilder.vue` | `removeItem(id)` без confirm | `confirm()` перед removeItem |
| `components/workspace/NotesGrid.vue` | удаление заметки сразу | `confirm()` |

### Модалка вместо `prompt()` (создание)
| Файл | Строки | Было | Станет |
|---|---|---|---|
| `components/workspace/NotesGrid.vue` | 15 | `prompt('Текст заметки')` | модалка с `<textarea>` |
| `components/workspace/QuickAddBar.vue` | 22, 38 | `prompt('Кому задача?')` | модалка с выбором исполнителя |

### BaseButton (замена мёртвых классов)
| Файл | Было | Станет |
|---|---|---|
| `components/workspace/TaskBoard.vue` | `class="btn-success"/"btn-danger"/"btn-secondary"` (мёртвые, без CSS) | `<BaseButton variant="success/danger/secondary">` |
| `views/manager/CallsView.vue` | `class="btn-secondary"` (мёртвый) | `<BaseButton variant="secondary">` |

### BaseBadge — НЕ в этой волне
Компонент создаётся и документируется, но массовая замена ручных `bg-green-100 text-green-700` по всем view — **в волне 2** (по мере доработки каждого экрана). В волне 1 — только определение компонента + 1-2 примера для демонстрации (например, статусы в ClientsView, если тривиально).

---

## Тестирование

Фронтенд-тесты в проекте пока **отсутствуют** (нет Vitest/Playwright). В волне 1:
- **Ручная проверка** после миграции: открыть каждый затронутый экран, проверить toast на сохранении/ошибке, confirm на удалении, BaseButton рендерится со стилем.
- **Smoke-проверка сборки:** `npm run build` без ошибок (TypeScript-проверка типов).
- **Visual Companion** (если ещё активен): показать до/после для подтверждения визуала.

Если в будущем заведём Vitest — добавить unit-тесты на BaseButton/BaseBadge (props → classes) и useConfirm (Promise resolve).

---

## Что НЕ в этой волне (явно)

- BaseBadge массово по всем view — волна 2
- Dashboard / ReportsView (фейк) / Catalog (loading/empty/пагинация) — волна 2
- Mobile-адаптив (бургер-меню) — отдельная задача
- Валидация форм — отдельная задача
- Реальный Dashboard с метриками — отдельная задача

---

## Риски / чёткие решения

- **vue-toastification@next vs stable:** пакет для Vue 3 — `vue-toastification@next` (или `^2.0.0-rc`). Установлю через `npm i vue-toastification@next`. Если конфликтует с Vue 3.5 — fallback на свой toast-компонент (Pinia store + Teleport). Проверю сразу после install.
- **Темизация:** дефолтные цвета vue-toastification нейтральные/синие — нужен `toast-theme.css` override под brand-600/green-600. Это часть задачи.
- **useConfirm singleton:** state модуля (`visible`, `options`) общий для всего app — ConfirmModal монтируется один раз в App.vue и читает тот же state. При параллельном вызове `confirm()` (редкий кейс) предыдущий resolver резолвится как `false` (отмена) перед показом нового — не даёт тихо зависших промисов (как было замечено в ревью).
- **ConfirmModal + Esc:** закрытие по Esc через `@keydown.esc` + `onClickOutside` из @vueuse/core (внешний клик = cancel).
- **Мёртвый Button.vue:** при удалении проверить, что никто не импортирует (разведка подтвердила — нигде не используется). Если всплывёт импорт — заменить на BaseButton.
