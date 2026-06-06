import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UserTask, TaskStatus } from '@/types/task'
import { tasksApi } from '@/api/tasks'

export const useTasksStore = defineStore('tasks', () => {
  const items = ref<UserTask[]>([])
  const loading = ref(false)

  async function list(params?: { status?: TaskStatus }) {
    loading.value = true
    try {
      const { data } = await tasksApi.list(params)
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<UserTask>) {
    const { data: created } = await tasksApi.create(data)
    items.value.unshift(created)
    return created
  }

  async function update(id: number, patch: Partial<UserTask>) {
    const { data } = await tasksApi.update(id, patch)
    const local = items.value.find((x) => x.id === id)
    if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    const deleteId = Number(id)
    await tasksApi.remove(deleteId)
    items.value = items.value.filter((x) => Number(x.id) !== deleteId)
  }

  return { items, loading, list, create, update, remove }
})
