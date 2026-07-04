import { api } from './client'
import type { Machine } from '@/types/machinery'

export const machineryApi = {
  list: (params?: { client_id?: number }) => api.get<Machine[]>('/api/machinery', { params }),
  create: (data: Partial<Machine>) => api.post<Machine>('/api/machinery', data),
  update: (id: number, data: Partial<Machine>) => api.patch<Machine>(`/api/machinery/${id}`, data),
  remove: (id: number) => api.delete(`/api/machinery/${id}`),
}
