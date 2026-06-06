import { defineStore } from 'pinia'
import { ref } from 'vue'
import { catalogApi } from '@/api/catalog'
import type { Sku } from '@/types/catalog'

export const useCatalogStore = defineStore('catalog', () => {
  const items = ref<Sku[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(params?: { category?: string; search?: string; d_min?: number; d_max?: number }) {
    loading.value = true
    error.value = null
    try {
      const { data } = await catalogApi.list(params)
      items.value = data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  return { items, loading, error, load }
})
