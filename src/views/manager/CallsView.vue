<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useCallsStore } from '@/stores/calls'
import { useTasksStore } from '@/stores/tasks'
import { useNotesStore } from '@/stores/notes'
import type { CallLog } from '@/types/call'

const calls = useCallsStore()
const tasks = useTasksStore()
const notes = useNotesStore()

const filter = ref<'all' | 'today' | 'week' | 'month'>('all')

const filtered = computed(() => {
  if (filter.value === 'all') return calls.list
  const now = new Date()

  return calls.list.filter((c) => {
    const d = new Date(c.call_date)
    if (filter.value === 'today') return d.toDateString() === now.toDateString()
    if (filter.value === 'week') return now.getTime() - d.getTime() < 7 * 86400000
    return now.getTime() - d.getTime() < 30 * 86400000
  })
})

onMounted(() => calls.load())

const pollingMs = 5000
let timer: number | undefined

const lastSeen = ref<{ id: number | null; updated_at: string | null }>({ id: null, updated_at: null })
const modalOpen = ref(false)
const modalCall = ref<CallLog | null>(null)

const popupTitle = computed(() => {
  if (!modalCall.value) return ''
  const c = modalCall.value
  if (c.status === 'in_progress') return `Звонок: ${c.client_name}`
  return `Обновление звонка: ${c.client_name}`
})

async function maybeTriggerPopup() {
  // опираемся на текущий уже загруженный список:
  // бэкенд сортирует по call_date desc + created_at desc
  if (!calls.list.length) return

  const latest = calls.list[0]
  if (!latest) return

  // корретней: сравним по updated_at именно для latest id
  const prevUpdatedAt =
    lastSeen.value.id === latest.id ? lastSeen.value.updated_at : null

  const latestUpdatedAt = latest.updated_at ?? null

  if (lastSeen.value.id === null || lastSeen.value.id !== latest.id || prevUpdatedAt !== latestUpdatedAt) {
    lastSeen.value = { id: latest.id, updated_at: latestUpdatedAt }

    // Показываем только если звонок ещё актуален:
    // in_progress или уже завершён/обработан.
    if (
      latest.status === 'in_progress' ||
      latest.status === 'completed' ||
      latest.status === 'no_answer' ||
      latest.status === 'rejected'
    ) {
      modalCall.value = latest
      modalOpen.value = true
    }
  }
}

// Важно: чтобы popup срабатывал по обновлению, делаем шаг:
// 1) load -> 2) сравнение и открытие.
async function refreshAndDetect() {
  await calls.load()
  await maybeTriggerPopup()
}

onMounted(() => {
  timer = window.setInterval(() => {
    void refreshAndDetect()
  }, pollingMs)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

function openModal(c: CallLog) {
  modalCall.value = c
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
  modalCall.value = null
}

async function onCreateTaskFromCall() {
  if (!modalCall.value) return
  const c = modalCall.value

  const titleDefault = c.status === 'in_progress' ? `Уточнить по звонку: ${c.client_name}` : `Следующее действие после звонка: ${c.client_name}`
  const title = prompt('Название задачи', titleDefault)?.trim()
  if (!title) return

  // backend: client_id = lead_id, call_id = call_logs.id
  await tasks.create({
    title,
    description: `Звонок (${c.status})\n${c.from_number ? `От: ${c.from_number}\n` : ''}${c.to_number ? `Кому: ${c.to_number}\n` : ''}`,
    status: 'todo',
    priority: 'medium',
    client_id: c.lead_id ?? undefined,
    call_id: c.id,
  })

  closeModal()
}

async function onAddNoteFromCall() {
  if (!modalCall.value) return
  const c = modalCall.value

  const title = prompt('Заголовок заметки', `Заметка по звонку: ${c.client_name}`)?.trim()
  if (!title) return

  const content =
    prompt('Текст заметки (можно пусто)', `Статус: ${c.status}\nДата: ${c.call_date}`)?.trim() ?? ''

  await notes.create({
    title,
    content,
    color: 'yellow',
    pinned: false,
    tags: [],
    client_id: c.lead_id ?? undefined,
  })

  closeModal()
}
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-3xl font-extrabold font-bebas tracking-wide">История звонков</h1>

    <div class="flex gap-2 bg-white rounded-xl border border-slate-200 p-1.5 shadow-sm w-fit">
      <button
        v-for="f in ['all','today','week','month']"
        :key="f"
        @click="filter=f as any"
        class="px-4 py-1.5 rounded-lg text-xs font-bold transition"
        :class="filter===f ? 'bg-brand-700 text-white' : 'text-neutral-500 hover:bg-slate-50'"
      >
        {{ f==='all'?'Все':f==='today'?'Сегодня':f==='week'?'Неделя':'Месяц' }}
      </button>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden p-5">
      <div class="space-y-4">
        <div
          v-for="c in filtered"
          :key="c.id"
          class="flex items-start gap-4 p-4 rounded-xl border border-slate-100 hover:bg-slate-50 transition"
        >
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-xs shrink-0"
            :class="
              c.status === 'completed' ? 'bg-green-100 text-green-700' :
              c.status === 'no_answer' ? 'bg-red-100 text-red-700' :
              c.status === 'in_progress' ? 'bg-amber-100 text-amber-700' :
              'bg-blue-100 text-blue-700'
            "
          >
            {{ c.status === 'completed' ? '✓' : c.status === 'no_answer' ? '✕' : c.status === 'in_progress' ? '…' : '⏱' }}
          </div>

          <div class="flex-1">
            <div class="flex items-center justify-between gap-2">
              <div class="font-bold text-sm">
                {{ c.client_name }}
              </div>
              <div class="text-[10px] text-neutral-400 font-bold whitespace-nowrap">
                {{ c.call_date }}
              </div>
            </div>

            <div class="mt-1 text-xs text-neutral-500">
              {{ c.notes }}
            </div>

            <div class="mt-2 flex items-center gap-2 flex-wrap">
              <span class="text-[10px] px-2 py-0.5 rounded bg-slate-50 border border-slate-200 text-slate-600">
                {{ c.status }}
              </span>

              <button
                class="btn-ghost text-[11px] px-2 py-1"
                @click="openModal(c)"
              >
                Действия
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Call popup -->
    <div
      v-if="modalOpen && modalCall"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="closeModal"
    >
      <div class="card w-full max-w-md p-5 space-y-4 bg-white border border-slate-200 rounded-2xl shadow-lg">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-lg font-extrabold">
              {{ popupTitle }}
            </h3>
            <p class="text-sm text-slate-500 mt-1">
              Статус: <span class="font-semibold">{{ modalCall?.status }}</span>
              <span v-if="modalCall?.call_date" class="ml-2">• {{ modalCall.call_date }}</span>
            </p>
          </div>
          <button class="btn-ghost !p-1" @click="closeModal" title="Закрыть">
            ✕
          </button>
        </div>

        <div class="space-y-2 text-sm">
          <div class="text-slate-600">
            {{ modalCall?.from_number ? `От: ${modalCall.from_number}` : '' }}
            <span v-if="modalCall?.from_number && modalCall?.to_number"> • </span>
            {{ modalCall?.to_number ? `Кому: ${modalCall.to_number}` : '' }}
          </div>
          <div v-if="modalCall?.notes" class="text-xs text-slate-500">
            {{ modalCall.notes }}
          </div>
        </div>

        <div class="flex gap-2 justify-end pt-2">
          <button class="btn-ghost text-sm" @click="closeModal">
            Отмена
          </button>
          <button class="btn-primary text-sm" @click="onCreateTaskFromCall">
            Создать задачу
          </button>
          <button class="btn-secondary text-sm" @click="onAddNoteFromCall">
            Добавить заметку
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
