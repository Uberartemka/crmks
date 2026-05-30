<script setup lang="ts">
import { computed, onMounted } from 'vue'
import draggable from 'vuedraggable'
import { useTasksStore } from '@/stores/tasks'
import type { TaskStatus, UserTask } from '@/types/task'
import TaskCard from './TaskCard.vue'
import { Plus } from 'lucide-vue-next'

const tasks = useTasksStore()
onMounted(() => tasks.list())

const COLUMNS: { id: TaskStatus; title: string; tint: string }[] = [
  { id: 'todo', title: 'К выполнению', tint: 'bg-slate-100' },
  { id: 'in_progress', title: 'В работе', tint: 'bg-blue-100' },
  { id: 'blocked', title: 'Заблокировано', tint: 'bg-red-100' },
  { id: 'done', title: 'Готово', tint: 'bg-emerald-100' },
]

const grouped = computed(() => {
  const map: Record<TaskStatus, UserTask[]> = { todo: [], in_progress: [], blocked: [], done: [] }
  for (const t of tasks.items) map[t.status].push(t)
  return map
})

function onChange(status: TaskStatus, evt: any) {
  const moved = evt.added?.element as UserTask | undefined
  if (moved && moved.status !== status) tasks.update(moved.id, { status })
}

async function quickAdd(status: TaskStatus) {
  const title = prompt('Название задачи?')
  if (title?.trim()) await tasks.create({ title: title.trim(), status, priority: 'medium' })
}
</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
    <div v-for="col in COLUMNS" :key="col.id" class="flex flex-col rounded-lg bg-white border border-slate-200">
      <div class="flex items-center justify-between px-3 py-2 border-b" :class="col.tint">
        <div class="flex items-center gap-2">
          <span class="font-semibold text-sm">{{ col.title }}</span>
          <span class="text-xs text-slate-500">{{ grouped[col.id].length }}</span>
        </div>
        <button class="btn-ghost !p-1" @click="quickAdd(col.id)" title="Добавить">
          <Plus :size="14" />
        </button>
      </div>

      <draggable
        :list="grouped[col.id]"
        group="tasks"
        item-key="id"
        class="flex-1 p-2 space-y-2 min-h-[100px]"
        @change="(e: any) => onChange(col.id, e)"
      >
        <template #item="{ element }">
          <TaskCard :task="element" @open="() => {}" />
        </template>
      </draggable>
    </div>
  </div>
</template>
