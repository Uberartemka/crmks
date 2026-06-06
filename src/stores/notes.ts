import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Note } from '@/types/note'
import { notesApi } from '@/api/notes'

export const useNotesStore = defineStore('notes', () => {
  const items = ref<Note[]>([])
  const loading = ref(false)

  async function list() {
    loading.value = true
    try {
      const { data } = await notesApi.list()
      items.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function create(data: Partial<Note>) {
    const { data: created } = await notesApi.create(data)
    items.value.unshift(created)
    return created
  }

  async function update(id: number, patch: Partial<Note>) {
    const { data } = await notesApi.update(id, patch)
    const local = items.value.find((x) => x.id === id)
    if (local) Object.assign(local, data)
    return data
  }

  async function remove(id: number) {
    await notesApi.remove(id)
    items.value = items.value.filter((x) => x.id !== id)
  }

  return { items, loading, list, create, update, remove }
})
