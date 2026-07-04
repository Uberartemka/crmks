import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Defect } from '@/types/defect'
import { defectsApi } from '@/api/defects'

export const useDefectsStore = defineStore('defects', () => {
  const items = ref<Defect[]>([])
  const loading = ref(false)

  async function load(params?: { client_id?: number }) {
    loading.value = true
    try {
      const { data } = await defectsApi.list(params)
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<Defect>) {
    const { data: created } = await defectsApi.create(data)
    items.value.unshift(created)
    return created
  }

  async function update(id: number, patch: Partial<Defect>) {
    const { data } = await defectsApi.update(id, patch)
    const local = items.value.find((x) => x.id === id)
    if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    await defectsApi.remove(id)
    items.value = items.value.filter((x) => x.id !== id)
  }

  return { items, loading, load, create, update, remove }
})
