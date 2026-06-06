import { api } from './client'
import type { CallLog, CallLogCreate } from '@/types/call'

export const callsApi = {
  list: () => api.get<CallLog[]>('/api/calls'),
  create: (data: CallLogCreate) => api.post<CallLog>('/api/calls', data),
  update: (id: number, data: CallLogCreate) =>
    api.put<{ status: string; id: number }>(`/api/calls/${id}`, data),
  delete: (id: number) => api.delete<{ status: string; id: number }>(`/api/calls/${id}`),
}
