import { api } from './client'
import type { Note } from '@/types/note'

export const notesApi = {
  list: () => api.get<Note[]>('/api/notes'),
  create: (data: Partial<Note>) => api.post<Note>('/api/notes', data),
  update: (id: number, data: Partial<Note>) => api.patch<Note>(`/api/notes/${id}`, data),
  remove: (id: number) => api.delete(`/api/notes/${id}`),
}
