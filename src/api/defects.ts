import { api } from './client'
import type { Defect } from '@/types/defect'

export const defectsApi = {
  list: (params?: { client_id?: number }) => api.get<Defect[]>('/api/defects', { params }),
  create: (data: Partial<Defect>) => api.post<Defect>('/api/defects', data),
  update: (id: number, data: Partial<Defect>) => api.patch<Defect>(`/api/defects/${id}`, data),
  remove: (id: number) => api.delete(`/api/defects/${id}`),
}
