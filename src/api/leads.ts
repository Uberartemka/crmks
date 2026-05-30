import { api } from './client'
import type { Lead, LeadAssign } from '@/types/lead'

export const leadsApi = {
  list: (params?: { query?: string; region?: string; status?: string; assigned_to?: number }) =>
    api.get<Lead[]>('/api/leads', { params }),
  create: (data: Record<string, any>) => api.post<{ id: number; status: string }>('/api/leads', data),
  assign: (id: number, data: LeadAssign) =>
    api.put<{ status: string; lead_id: number; assigned_to?: number }>(`/api/leads/${id}/assign`, data),
  updateStatus: (id: number, status: string) =>
    api.put(`/api/leads/${id}/status`, { status }),
}
