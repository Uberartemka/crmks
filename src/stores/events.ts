import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CalendarEvent } from '@/types/event'
import { eventsApi } from '@/api/events'

export const useEventsStore = defineStore('events', () => {
  const items = ref<CalendarEvent[]>([])
  const loading = ref(false)

  async function list(params?: { from?: string; to?: string }) {
    loading.value = true
    try {
      const { data } = await eventsApi.list(params)
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<CalendarEvent>) {
    const { data: created } = await eventsApi.create(data)
    items.value.push(created)
    return created
  }

  async function update(id: number, patch: Partial<CalendarEvent>) {
    const { data } = await eventsApi.update(id, patch)
    const l = items.value.find((x) => x.id === id)
    if (l) Object.assign(l, data)
    return data
  }

  async function remove(id: number) {
    await eventsApi.remove(id)
    items.value = items.value.filter((x) => x.id !== id)
  }

  return { items, loading, list, create, update, remove }
})
