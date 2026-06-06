import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CalendarEvent } from '@/types/event'
import { eventsApi } from '@/api/events'

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'
let mockId = 300

function isoToday(h: number, addDays = 0) {
  const d = new Date(); d.setDate(d.getDate() + addDays); d.setHours(h, 0, 0, 0)
  return d.toISOString()
}

const mockEvents: CalendarEvent[] = [
  { id: 1, title: 'Встреча с АгроХолдинг-Юг', kind: 'meeting', start: isoToday(11), end: isoToday(12), all_day: false, location: 'Zoom', color: 'blue', created_at: '', updated_at: '' },
  { id: 2, title: 'Дедлайн ТЭО Сибмаш', kind: 'deadline', start: isoToday(18, 2), all_day: true, color: 'red', created_at: '', updated_at: '' },
  { id: 3, title: 'Звонок инженеру', kind: 'call', start: isoToday(15, 1), end: isoToday(16, 1), all_day: false, color: 'green', created_at: '', updated_at: '' },
  { id: 4, title: 'Презентация каталога', kind: 'meeting', start: isoToday(10, 5), end: isoToday(11, 5), all_day: false, color: 'purple', created_at: '', updated_at: '' },
]

export const useEventsStore = defineStore('events', () => {
  const items = ref<CalendarEvent[]>([])
  const loading = ref(false)

  async function list(params?: { from?: string; to?: string }) {
    loading.value = true
    try {
      if (USE_MOCKS) { items.value = [...mockEvents]; return items.value }
      const { data } = await eventsApi.list(params); items.value = data; return data
    } finally { loading.value = false }
  }

  async function create(data: Partial<CalendarEvent>) {
    if (USE_MOCKS) {
      const now = new Date().toISOString()
      const ev: CalendarEvent = {
        id: ++mockId, title: data.title ?? 'Событие', kind: data.kind ?? 'meeting',
        start: data.start ?? new Date().toISOString(), end: data.end, all_day: data.all_day ?? false,
        location: data.location, description: data.description,
        color: data.color ?? 'blue', created_at: now, updated_at: now,
      }
      mockEvents.push(ev); items.value.push(ev); return ev
    }
    const { data: created } = await eventsApi.create(data)
    items.value.push(created); return created
  }

  async function update(id: number, patch: Partial<CalendarEvent>) {
    if (USE_MOCKS) {
      const e = mockEvents.find(x => x.id === id); if (!e) throw new Error('not found')
      Object.assign(e, patch, { updated_at: new Date().toISOString() })
      const l = items.value.find(x => x.id === id); if (l) Object.assign(l, e)
      return e
    }
    const { data } = await eventsApi.update(id, patch)
    const l = items.value.find(x => x.id === id); if (l) Object.assign(l, data)
    return data
  }

  async function remove(id: number) {
    if (USE_MOCKS) {
      const i = mockEvents.findIndex(x => x.id === id); if (i >= 0) mockEvents.splice(i, 1)
      items.value = items.value.filter(x => x.id !== id); return
    }
    await eventsApi.remove(id)
    items.value = items.value.filter(x => x.id !== id)
  }

  return { items, loading, list, create, update, remove }
})
