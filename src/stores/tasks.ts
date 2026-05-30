import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UserTask, TaskStatus } from '@/types/task'
import { tasksApi } from '@/api/tasks'

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

let mockId = 100
const mockTasks: UserTask[] = [
  {
    id: 1, title: 'Перезвонить инженеру АгроХолдинг-Юг', status: 'todo', priority: 'high',
    due_date: new Date(Date.now() + 86400000).toISOString(), tags: ['клиент', 'звонок'],
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
  {
    id: 2, title: 'Подготовить ТЭО для завода Сибмаш', status: 'in_progress', priority: 'urgent',
    description: 'Расчёт ROI замены подшипников на линии №3', tags: ['ТЭО'],
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
  {
    id: 3, title: 'Согласовать счёт №2041', status: 'blocked', priority: 'medium',
    tags: ['счёт'], created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
  {
    id: 4, title: 'Отправить КП клиенту Норильск-Логистик', status: 'done', priority: 'medium',
    tags: ['КП'], created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  },
]

export const useTasksStore = defineStore('tasks', () => {
  const items = ref<UserTask[]>([])
  const loading = ref(false)

  async function list(params?: { status?: TaskStatus }) {
    loading.value = true
    try {
      if (USE_MOCKS) {
        items.value = params?.status ? mockTasks.filter(t => t.status === params.status) : [...mockTasks]
      } else {
        const { data } = await tasksApi.list(params)
        items.value = data
      }
      return items.value
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<UserTask>) {
    if (USE_MOCKS) {
      const now = new Date().toISOString()
      const task: UserTask = {
        id: ++mockId, title: data.title ?? 'Без названия', status: data.status ?? 'todo',
        priority: data.priority ?? 'medium', description: data.description, due_date: data.due_date,
        tags: data.tags ?? [], created_at: now, updated_at: now,
      }
      mockTasks.unshift(task); items.value.unshift(task)
      return task
    }
    const { data: created } = await tasksApi.create(data)
    items.value.unshift(created); return created
  }

  async function update(id: number, patch: Partial<UserTask>) {
    if (USE_MOCKS) {
      const t = mockTasks.find((x: UserTask) => x.id === id); if (!t) throw new Error('not found')
      Object.assign(t, patch, { updated_at: new Date().toISOString() })
      const local = items.value.find((x: UserTask) => x.id === id); if (local) Object.assign(local, t)
      return t
    }
    const { data } = await tasksApi.update(id, patch)
    const local = items.value.find((x: UserTask) => x.id === id); if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    if (USE_MOCKS) {
      const i = mockTasks.findIndex((x: UserTask) => x.id === id); if (i >= 0) mockTasks.splice(i, 1)
      items.value = items.value.filter((x: UserTask) => x.id !== id); return
    }
    await tasksApi.remove(id)
    items.value = items.value.filter((x: UserTask) => x.id !== id)
  }

  return { items, loading, list, create, update, remove }
})
