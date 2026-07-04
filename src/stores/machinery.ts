import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Machine } from '@/types/machinery'
import { machineryApi } from '@/api/machinery'

export const useMachineryStore = defineStore('machinery', () => {
  const items = ref<Machine[]>([])
  const loading = ref(false)

  async function load(params?: { client_id?: number }) {
    loading.value = true
    try {
      const { data } = await machineryApi.list(params)
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<Machine>) {
    const { data: created } = await machineryApi.create(data)
    items.value.unshift(created)
    return created
  }

  async function update(id: number, patch: Partial<Machine>) {
    const { data } = await machineryApi.update(id, patch)
    const local = items.value.find((x) => x.id === id)
    if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    await machineryApi.remove(id)
    items.value = items.value.filter((x) => x.id !== id)
  }

  return { items, loading, load, create, update, remove }
})
