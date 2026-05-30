<script setup lang="ts">
import { computed } from 'vue'
import {
  monthGridDays, isSameMonth, isToday, format, colorClasses, itemsOnDay,
} from '@/lib/calendar'
import { ru } from 'date-fns/locale'
import type { CalendarItem } from '@/types/event'

const props = defineProps<{ anchor: Date; items: CalendarItem[] }>()
const emit = defineEmits<{
  (e: 'pick-day', d: Date): void
  (e: 'open-item', i: CalendarItem): void
}>()

const days = computed(() => monthGridDays(props.anchor))
const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const MAX_VISIBLE = 3
</script>

<template>
  <div class="card overflow-hidden">
    <div class="grid grid-cols-7 border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
      <div v-for="w in weekdays" :key="w" class="px-2 py-1.5 text-center">{{ w }}</div>
    </div>

    <div class="grid grid-cols-7 grid-rows-6 h-[600px]">
      <div
        v-for="day in days" :key="day.toISOString()"
        class="border-b border-r border-slate-100 p-1 flex flex-col gap-0.5 cursor-pointer hover:bg-slate-50 transition"
        :class="{ 'bg-slate-50/50 text-slate-400': !isSameMonth(day, anchor) }"
        @click="emit('pick-day', day)"
      >
        <div class="flex items-center justify-between text-xs">
          <span
            class="inline-flex items-center justify-center w-6 h-6 rounded-full"
            :class="isToday(day) ? 'bg-brand-600 text-white font-semibold' : 'text-slate-700'"
          >
            {{ format(day, 'd', { locale: ru }) }}
          </span>
        </div>

        <div class="flex-1 space-y-0.5 overflow-hidden">
          <button
            v-for="item in itemsOnDay(items, day).slice(0, MAX_VISIBLE)" :key="item.id"
            class="w-full text-left text-[11px] px-1.5 py-0.5 rounded truncate flex items-center gap-1"
            :class="[colorClasses(item.color as any).bg, colorClasses(item.color as any).text]"
            @click.stop="emit('open-item', item)"
          >
            <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="colorClasses(item.color as any).dot" />
            <span class="truncate">{{ item.title }}</span>
          </button>
          <div
            v-if="itemsOnDay(items, day).length > MAX_VISIBLE"
            class="text-[10px] text-slate-500 px-1.5"
          >
            + ещё {{ itemsOnDay(items, day).length - MAX_VISIBLE }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
