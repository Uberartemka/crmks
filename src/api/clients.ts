import { api } from './client'
import type { Client, ClientCreate } from '@/types/client'

export const clientsApi = {
  list: () => api.get<Client[]>('/api/clients'),
  create: (data: ClientCreate) =>
    api.post<{ status: string; client_id: number }>('/api/clients', data),
  get: (id: number) => api.get<Client>(`/api/clients/${id}`),
  delete: (id: number) => api.delete<{ status: string; client_id: number }>(`/api/clients/${id}`),
  searchEmail: (q: string) => api.get<{ email: string | null; source: string | null }>('/api/search/email', { params: { q } }),
}
