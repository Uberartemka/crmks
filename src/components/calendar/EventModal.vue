<script setup lang="ts">
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import type { CalendarEvent, EventKind } from '@/types/event'
import { useEventsStore } from '@/stores/events'

const props = defineProps<{ open: boolean; event?: CalendarEvent | null; defaultDate?: Date | null }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()
const events = useEventsStore()

const form = ref({
  title: '', description: '', kind: 'meeting' as EventKind,
  start: '', end: '', all_day: false, location: '',
  color: 'blue' as NonNullable<CalendarEvent['color']>,
})

function toInput(d: Date | string, allDay: boolean) {
  const date = typeof d === 'string' ? new Date(d) : d
  if (allDay) return date.toISOString().slice(0, 10)
  // datetime-local format
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

watch(() => props.open, (o) => {
  if (!o) return
  if (props.event) {
    form.value = {
      title: props.event.title,
      description: props.event.description ?? '',
      kind: props.event.kind,
      start: toInput(props.event.start, props.event.all_day),
      end: props.event.end ? toInput(props.event.end, props.event.all_day) : '',
      all_day: props.event.all_day,
      location: props.event.location ?? '',
      color: props.event.color ?? 'blue',
    }
  } else {
    const base = props.defaultDate ?? new Date()
    base.setMinutes(0, 0, 0); if (!props.defaultDate) base.setHours(base.getHours() + 1)
    form.value = {
      title: '', description: '', kind: 'meeting',
      start: toInput(base, false),
      end: toInput(new Date(base.getTime() + 60 * 60 * 1000), false),
      all_day: false, location: '', color: 'blue',
    }
  }
})

async function save() {
  if (!form.value.title.trim()) return
  const payload: Partial<CalendarEvent> = {
    title: form.value.title.trim(),
    description: form.value.description || undefined,
    kind: form.value.kind,
    start: new Date(form.value.start).toISOString(),
    end: form.value.end ? new Date(form.value.end).toISOString() : undefined,
    all_day: form.value.all_day,
    location: form.value.location || undefined,
    color: form.value.color,
  }
  if (props.event) await events.update(props.event.id, payload)
  else await events.create(payload)
  emit('saved'); emit('close')
}

async function del() {
  if (!props.event) return
  if (!confirm('Удалить событие?')) return
  await events.remove(props.event.id)
  emit('saved'); emit('close')
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="emit('close')">
    <div class="card w-full max-w-md p-4 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="font-semibold">{{ event ? 'Редактировать' : 'Новое событие' }}</h3>
        <button class="btn-ghost !p-1" @click="emit('close')"><X :size="16" /></button>
      </div>

      <input v-model="form.title" class="input" placeholder="Название" autofocus />

      <div class="grid grid-cols-2 gap-2">
        <select v-model="form.kind" class="input">
          <option value="meeting">Встреча</option>
          <option value="call">Звонок</option>
          <option value="deadline">Дедлайн</option>
          <option value="reminder">Напоминание</option>
        </select>
        <select v-model="form.color" class="input">
          <option value="blue">Синий</option>
          <option value="green">Зелёный</option>
          <option value="orange">Оранжевый</option>
          <option value="red">Красный</option>
          <option value="purple">Фиолетовый</option>
        </select>
      </div>

      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" v-model="form.all_day" /> Весь день
      </label>

      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="text-xs text-slate-500">Начало</label>
          <input :type="form.all_day ? 'date' : 'datetime-local'" v-model="form.start" class="input" />
        </div>
        <div>
          <label class="text-xs text-slate-500">Конец</label>
          <input :type="form.all_day ? 'date' : 'datetime-local'" v-model="form.end" class="input" />
        </div>
      </div>

      <input v-model="form.location" class="input" placeholder="Место / ссылка (Zoom, адрес)" />
      <textarea v-model="form.description" rows="2" class="input resize-none" placeholder="Описание" />

      <div class="flex items-center justify-between pt-1">
        <button v-if="event" class="text-xs text-red-600 hover:underline" @click="del">Удалить</button>
        <div class="flex gap-2 ml-auto">
          <button class="btn-ghost text-sm" @click="emit('close')">Отмена</button>
          <button class="btn-primary text-sm" @click="save">Сохранить</button>
        </div>
      </div>
    </div>
  </div>
</template>
