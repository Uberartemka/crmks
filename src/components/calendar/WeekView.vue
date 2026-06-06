<script setup lang="ts">
import { computed } from 'vue'
import { weekDays, dayHours, format, isToday, colorClasses, isSameDay } from '@/lib/calendar'
import { ru } from 'date-fns/locale'
import type { CalendarItem } from '@/types/event'

const props = defineProps<{ anchor: Date; items: CalendarItem[] }>()
const emit = defineEmits<{
  (e: 'pick-slot', d: Date): void
  (e: 'open-item', i: CalendarItem): void
}>()

const days = computed(() => weekDays(props.anchor))
const hours = dayHours()

function itemsAt(day: Date, hour: number) {
  return props.items.filter(i =>
    !i.all_day && isSameDay(i.start, day) && i.start.getHours() === hour
  )
}
function allDayItems(day: Date) {
  return props.items.filter(i => i.all_day && isSameDay(i.start, day))
}

function pick(day: Date, hour: number) {
  const d = new Date(day); d.setHours(hour, 0, 0, 0); emit('pick-slot', d)
}
</script>

<template>
  <div class="card overflow-hidden">
    <!-- header дней -->
    <div class="grid border-b border-slate-200 bg-slate-50 text-xs" style="grid-template-columns: 60px repeat(7, 1fr)">
      <div></div>
      <div v-for="d in days" :key="d.toISOString()" class="px-2 py-1.5 text-center border-l border-slate-100">
        <div class="text-slate-500">{{ format(d, 'EEE', { locale: ru }) }}</div>
        <div
          class="inline-flex items-center justify-center w-7 h-7 rounded-full text-sm"
          :class="isToday(d) ? 'bg-brand-600 text-white font-semibold' : ''"
        >{{ format(d, 'd', { locale: ru }) }}</div>
      </div>
    </div>

    <!-- all-day строка -->
    <div class="grid border-b border-slate-200 bg-slate-50/50 min-h-[32px]" style="grid-template-columns: 60px repeat(7, 1fr)">
      <div class="text-[10px] text-slate-400 px-2 py-1">весь день</div>
      <div v-for="d in days" :key="d.toISOString()" class="border-l border-slate-100 p-1 space-y-0.5">
        <button v-for="it in allDayItems(d)" :key="it.id"
          class="w-full text-left text-[11px] px-1.5 py-0.5 rounded truncate"
          :class="[colorClasses(it.color as any).bg, colorClasses(it.color as any).text]"
          @click="emit('open-item', it)"
        >{{ it.title }}</button>
      </div>
    </div>

    <!-- сетка часов -->
    <div class="max-h-[540px] overflow-y-auto">
      <div v-for="h in hours" :key="h" class="grid border-b border-slate-100" style="grid-template-columns: 60px repeat(7, 1fr); height: 48px">
        <div class="text-[11px] text-slate-400 pr-2 pt-0.5 text-right">{{ String(h).padStart(2, '0') }}:00</div>
        <div
          v-for="d in days" :key="d.toISOString() + h"
          class="border-l border-slate-100 relative cursor-pointer hover:bg-slate-50"
          @click="pick(d, h)"
        >
          <button v-for="it in itemsAt(d, h)" :key="it.id"
            class="absolute inset-x-1 top-0.5 text-[11px] px-1.5 py-0.5 rounded truncate text-left"
            :class="[colorClasses(it.color as any).bg, colorClasses(it.color as any).text]"
            @click.stop="emit('open-item', it)"
          >{{ it.title }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
