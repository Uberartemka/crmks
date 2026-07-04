import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Order } from '@/types/order'
import { ordersApi } from '@/api/orders'

export const useOrdersStore = defineStore('orders', () => {
  const items = ref<Order[]>([])
  const loading = ref(false)

  async function load(params?: { client_id?: number }) {
    loading.value = true
    try {
      const { data } = await ordersApi.list(params)
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<Order>) {
    const { data: created } = await ordersApi.create(data)
    items.value.unshift(created)
    return created
  }

  async function update(id: number, patch: Partial<Order>) {
    const { data } = await ordersApi.update(id, patch)
    const local = items.value.find((x) => x.id === id)
    if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    await ordersApi.remove(id)
    items.value = items.value.filter((x) => x.id !== id)
  }

  return { items, loading, load, create, update, remove }
})
