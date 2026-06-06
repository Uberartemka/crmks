import { defineStore } from 'pinia'
import { ref } from 'vue'
import { leadsApi } from '@/api/leads'
import type { Lead } from '@/types/lead'

export const useLeadsStore = defineStore('leads', () => {
  const list = ref<Lead[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(params?: { query?: string; region?: string; status?: string; assigned_to?: number }) {
    loading.value = true
    error.value = null
    try {
      const { data } = await leadsApi.list(params)
      list.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function create(data: Record<string, any>) {
    const res = await leadsApi.create(data)
    await load()
    return res.data
  }

  async function assign(id: number, userId?: number) {
    await leadsApi.assign(id, { user_id: userId })
    await load()
  }

  async function updateStatus(id: number, status: string) {
    await leadsApi.updateStatus(id, status)
    await load()
  }

  return { list, loading, error, load, create, assign, updateStatus }
})
