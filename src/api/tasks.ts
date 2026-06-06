import { api } from './client'
import type { UserTask } from '@/types/task'

export const tasksApi = {
  list: (params?: { status?: string; client_id?: number }) =>
    api.get<UserTask[]>('/api/tasks', { params }),
  create: (data: Partial<UserTask>) => api.post<UserTask>('/api/tasks', data),
  update: (id: number, data: Partial<UserTask>) =>
    api.patch<UserTask>(`/api/tasks/${id}`, data),
  remove: (id: number) => api.delete(`/api/tasks/${id}`),
}
