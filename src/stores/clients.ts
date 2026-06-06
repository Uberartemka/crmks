import { defineStore } from 'pinia'
import { ref } from 'vue'
import { clientsApi } from '@/api/clients'
import type { Client, ClientCreate } from '@/types/client'

export const useClientsStore = defineStore('clients', () => {
  const list = ref<Client[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const { data } = await clientsApi.list()
      list.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function create(data: ClientCreate) {
    const res = await clientsApi.create(data)
    await load()
    return res.data
  }

  async function remove(id: number) {
    await clientsApi.delete(id)
    await load()
  }

  return { list, loading, error, load, create, remove }
})
