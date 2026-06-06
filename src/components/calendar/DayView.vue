<script setup lang="ts">
import { computed } from 'vue'
import { dayHours, format, colorClasses, isSameDay } from '@/lib/calendar'
import { ru } from 'date-fns/locale'
import type { CalendarItem } from '@/types/event'

const props = defineProps<{ anchor: Date; items: CalendarItem[] }>()
const emit = defineEmits<{
  (e: 'pick-slot', d: Date): void
  (e: 'open-item', i: CalendarItem): void
}>()

const hours = dayHours()
const dayItems = computed(() => props.items.filter(i => isSameDay(i.start, props.anchor)))

function itemsAt(hour: number) {
  return dayItems.value.filter(i => !i.all_day && i.start.getHours() === hour)
}
const allDay = computed(() => dayItems.value.filter(i => i.all_day))

function pick(hour: number) {
  const d = new Date(props.anchor); d.setHours(hour, 0, 0, 0); emit('pick-slot', d)
}
</script>

<template>
  <div class="card overflow-hidden">
    <div class="px-3 py-2 border-b border-slate-200 bg-slate-50">
      <div class="font-semibold">{{ format(anchor, 'EEEE, d MMMM yyyy', { locale: ru }) }}</div>
    </div>

    <div v-if="allDay.length" class="px-3 py-2 border-b border-slate-100 space-y-1 bg-slate-50/30">
      <div class="text-[10px] uppercase text-slate-400">весь день</div>
      <button v-for="it in allDay" :key="it.id"
        class="w-full text-left text-sm px-2 py-1 rounded"
        :class="[colorClasses(it.color as any).bg, colorClasses(it.color as any).text]"
        @click="emit('open-item', it)"
      >{{ it.title }}</button>
    </div>

    <div class="max-h-[600px] overflow-y-auto">
      <div v-for="h in hours" :key="h" class="grid border-b border-slate-100" style="grid-template-columns: 60px 1fr; height: 56px">
        <div class="text-xs text-slate-400 pr-2 pt-1 text-right">{{ String(h).padStart(2, '0') }}:00</div>
        <div class="relative cursor-pointer hover:bg-slate-50" @click="pick(h)">
          <button v-for="it in itemsAt(h)" :key="it.id"
            class="absolute inset-x-2 top-1 text-sm px-2 py-1 rounded text-left"
            :class="[colorClasses(it.color as any).bg, colorClasses(it.color as any).text]"
            @click.stop="emit('open-item', it)"
          >
            <div class="font-medium truncate">{{ it.title }}</div>
            <div class="text-[11px] opacity-75">{{ format(it.start, 'HH:mm') }}<span v-if="it.end"> – {{ format(it.end, 'HH:mm') }}</span></div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
