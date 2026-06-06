import { defineStore } from 'pinia'
import { ref } from 'vue'
import { callsApi } from '@/api/calls'
import type { CallLog, CallLogCreate } from '@/types/call'

export const useCallsStore = defineStore('calls', () => {
  const list = ref<CallLog[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const { data } = await callsApi.list()
      list.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function create(data: CallLogCreate) {
    const res = await callsApi.create(data)
    await load()
    return res.data
  }

  async function update(id: number, data: CallLogCreate) {
    await callsApi.update(id, data)
    await load()
  }

  async function remove(id: number) {
    await callsApi.delete(id)
    await load()
  }

  return { list, loading, error, load, create, update, remove }
})
