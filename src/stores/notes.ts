import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Note } from '@/types/note'
import { notesApi } from '@/api/notes'

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'
let mockId = 200
const mockNotes: Note[] = [
  { id: 1, title: 'Аналог SKF 6205', content: 'Клиент готов на замену **NSK 6205DDU**. Срок 3 дня.', color: 'yellow', pinned: true, tags: ['аналог'], created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
  { id: 2, title: 'Совещание с Сибмаш', content: '- ISO 281 расчёт по линии 3\n- Жду чертежи', color: 'blue', pinned: false, tags: ['встреча'], created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
  { id: 3, title: 'Идея', content: 'Добавить в каталог фильтр по ГОСТ', color: 'green', pinned: false, tags: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
]

export const useNotesStore = defineStore('notes', () => {
  const items = ref<Note[]>([])
  const loading = ref(false)

  async function list() {
    loading.value = true
    try {
      if (USE_MOCKS) { items.value = [...mockNotes]; return items.value }
      const { data } = await notesApi.list(); items.value = data; return data
    } finally { loading.value = false }
  }

  async function create(data: Partial<Note>) {
    if (USE_MOCKS) {
      const now = new Date().toISOString()
      const n: Note = { id: ++mockId, title: data.title ?? 'Заметка', content: data.content ?? '', color: data.color ?? 'yellow', pinned: false, tags: data.tags ?? [], created_at: now, updated_at: now }
      mockNotes.unshift(n); items.value.unshift(n); return n
    }
    const { data: created } = await notesApi.create(data)
    items.value.unshift(created); return created
  }

  async function update(id: number, patch: Partial<Note>) {
    if (USE_MOCKS) {
      const n = mockNotes.find((x: Note) => x.id === id); if (!n) throw new Error('not found')
      Object.assign(n, patch, { updated_at: new Date().toISOString() })
      const l = items.value.find((x: Note) => x.id === id); if (l) Object.assign(l, n)
      return n
    }
    const { data } = await notesApi.update(id, patch)
    const l = items.value.find((x: Note) => x.id === id); if (l) Object.assign(l, data)
    return data
  }

  async function remove(id: number) {
    if (USE_MOCKS) {
      const i = mockNotes.findIndex((x: Note) => x.id === id); if (i >= 0) mockNotes.splice(i, 1)
      items.value = items.value.filter((x: Note) => x.id !== id); return
    }
    await notesApi.remove(id)
    items.value = items.value.filter((x: Note) => x.id !== id)
  }

  return { items, loading, list, create, update, remove }
})
