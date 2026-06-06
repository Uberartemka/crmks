<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-vue-next'
import { format, addMonths, addWeeks, addDays, buildItems } from '@/lib/calendar'
import { ru } from 'date-fns/locale'
import MonthView from './MonthView.vue'
import WeekView from './WeekView.vue'
import DayView from './DayView.vue'
import EventModal from './EventModal.vue'
import { useEventsStore } from '@/stores/events'
import { useTasksStore } from '@/stores/tasks'
import type { CalendarItem, CalendarEvent } from '@/types/event'

type Mode = 'month' | 'week' | 'day'
const mode = ref<Mode>('month')
const anchor = ref(new Date())

const events = useEventsStore()
const tasks = useTasksStore()

const items = computed<CalendarItem[]>(() => buildItems(events.items, tasks.items))

onMounted(() => {
  events.list()
  if (!tasks.items.length) tasks.list()
})

const title = computed(() => {
  if (mode.value === 'month') return format(anchor.value, 'LLLL yyyy', { locale: ru })
  if (mode.value === 'week') return `Неделя ${format(anchor.value, 'w, LLLL yyyy', { locale: ru })}` 
  return format(anchor.value, 'd MMMM yyyy', { locale: ru })
})

function shift(dir: -1 | 1) {
  if (mode.value === 'month') anchor.value = addMonths(anchor.value, dir)
  else if (mode.value === 'week') anchor.value = addWeeks(anchor.value, dir)
  else anchor.value = addDays(anchor.value, dir)
}
function today() { anchor.value = new Date() }

// modal
const modalOpen = ref(false)
const editing = ref<CalendarEvent | null>(null)
const defaultDate = ref<Date | null>(null)

function newEvent(d?: Date) {
  editing.value = null; defaultDate.value = d ?? new Date(); modalOpen.value = true
}
function openItem(it: CalendarItem) {
  if (it.source === 'event') {
    editing.value = events.items.find(e => e.id === it.ref_id) ?? null
    defaultDate.value = null
    modalOpen.value = true
  }
  // task — оставим клик пустым, либо открой модалку задачи когда сделаем
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="flex items-center gap-1">
        <button class="btn-ghost !p-1.5" @click="shift(-1)"><ChevronLeft :size="16" /></button>
        <button class="btn-ghost text-xs" @click="today">Сегодня</button>
        <button class="btn-ghost !p-1.5" @click="shift(1)"><ChevronRight :size="16" /></button>
        <h2 class="font-semibold text-lg ml-2 capitalize">{{ title }}</h2>
      </div>

      <div class="flex items-center gap-2">
        <div class="flex gap-0.5 bg-white border border-slate-200 rounded-md p-0.5">
          <button class="btn-ghost text-xs" :class="{ '!bg-brand-50 !text-brand-700': mode==='month' }" @click="mode='month'">Месяц</button>
          <button class="btn-ghost text-xs" :class="{ '!bg-brand-50 !text-brand-700': mode==='week' }" @click="mode='week'">Неделя</button>
          <button class="btn-ghost text-xs" :class="{ '!bg-brand-50 !text-brand-700': mode==='day' }" @click="mode='day'">День</button>
        </div>
        <button class="btn-primary text-sm" @click="newEvent()">
          <Plus :size="14" /> Событие
        </button>
      </div>
    </div>

    <MonthView v-if="mode==='month'" :anchor="anchor" :items="items"
      @pick-day="(d) => newEvent(d)" @open-item="openItem" />
    <WeekView v-else-if="mode==='week'" :anchor="anchor" :items="items"
      @pick-slot="(d) => newEvent(d)" @open-item="openItem" />
    <DayView v-else :anchor="anchor" :items="items"
      @pick-slot="(d) => newEvent(d)" @open-item="openItem" />

    <EventModal
      :open="modalOpen" :event="editing" :default-date="defaultDate"
      @close="modalOpen=false" @saved="events.list()"
    />
  </div>
</template>
