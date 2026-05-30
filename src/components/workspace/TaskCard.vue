<script setup lang="ts">
import type { UserTask, TaskPriority } from '@/types/task'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'

defineProps<{ task: UserTask }>()
defineEmits<{ (e: 'open', task: UserTask): void }>()

const priorityColor: Record<TaskPriority, string> = {
  low: 'bg-slate-100 text-slate-600',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  urgent: 'bg-red-100 text-red-700',
}
</script>

<template>
  <div
    class="card p-3 cursor-pointer hover:shadow-md transition"
    @click="$emit('open', task)"
  >
    <div class="flex items-start justify-between gap-2">
      <h4 class="font-medium text-sm leading-tight">{{ task.title }}</h4>
      <span class="text-[10px] uppercase px-1.5 py-0.5 rounded" :class="priorityColor[task.priority]">
        {{ task.priority }}
      </span>
    </div>

    <p v-if="task.description" class="mt-1 text-xs text-slate-500 line-clamp-2">
      {{ task.description }}
    </p>

    <div class="mt-2 flex items-center justify-between text-[11px] text-slate-500">
      <span v-if="task.due_date">
        📅 {{ format(new Date(task.due_date), 'd MMM', { locale: ru }) }}
      </span>
      <div class="flex gap-1 flex-wrap">
        <span v-for="t in task.tags" :key="t" class="px-1.5 py-0.5 rounded bg-slate-100">
          #{{ t }}
        </span>
      </div>
    </div>
  </div>
</template>
