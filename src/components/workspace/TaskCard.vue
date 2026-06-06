<script setup lang="ts">
import type { UserTask, TaskPriority } from '@/types/task'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ task: UserTask }>()
defineEmits<{ (e: 'open', task: UserTask): void }>()

const priorityColor: Record<TaskPriority, string> = {
  low: 'bg-slate-100 text-slate-600',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  urgent: 'bg-red-100 text-red-700',
}

type DeadlineTone = 'green' | 'yellow' | 'red' | 'none'

function getDeadlineTone(dueDate: string | undefined, nowMs: number): DeadlineTone {
  if (!dueDate) return 'none'
  const dueMs = new Date(dueDate).getTime()
  if (!Number.isFinite(dueMs)) return 'none'

  const diffHours = (dueMs - nowMs) / (1000 * 60 * 60)

  // <= 24ч (или просрочено)
  if (diffHours <= 24) return 'red'
  // <= 72ч
  if (diffHours <= 72) return 'yellow'
  return 'green'
}

const nowMs = ref(Date.now())
let timer: number | undefined

onMounted(() => {
  timer = window.setInterval(() => {
    nowMs.value = Date.now()
  }, 60_000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

const deadlineTone = computed(() => getDeadlineTone(props.task.due_date, nowMs.value))

const deadlineClass = computed(() => {
  switch (deadlineTone.value) {
    case 'green':
      return 'border-2 border-emerald-300 bg-emerald-50/40'
    case 'yellow':
      return 'border-2 border-amber-300 bg-amber-50/40'
    case 'red':
      return 'border-2 border-red-300 bg-red-50/40'
    default:
      return ''
  }
})

const finalClass = computed(() => {
  if (props.task.status === 'done') {
    return 'border-2 border-emerald-500 bg-emerald-50/60'
  }
  return deadlineClass.value
})
</script>

<template>
  <div
    class="card p-3 cursor-pointer hover:shadow-md transition"
    :class="finalClass"
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
