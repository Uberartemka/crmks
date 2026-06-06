import { api } from './client'
import type { Proposal, ProposalInput, ProposalItemInput, DiscountInput, SendEmailInput } from '@/types/proposal'

export const proposalsApi = {
  list: () => api.get<Proposal[]>('/api/proposals'),
  create: (data: ProposalInput) =>
    api.post<{ status: string; proposal_id: number; seq_num: number }>('/api/proposals', data),
  get: (id: number) => api.get<Proposal>(`/api/proposals/${id}`),
  delete: (id: number) => api.delete<{ status: string; proposal_id: number }>(`/api/proposals/${id}`),
  deleteAll: () => api.delete<{ status: string }>('/api/proposals'),
  setDiscount: (id: number, data: DiscountInput) =>
    api.post<{ status: string; discount_global: number }>(`/api/proposals/${id}/discount`, data),
  send: (id: number, data?: SendEmailInput) =>
    api.post<{ status: string; proposal_id: number; recipient: string }>(`/api/proposals/${id}/send`, data || {}),
  addItem: (proposalId: number, data: ProposalItemInput) =>
    api.post(`/api/proposals/${proposalId}/items`, data),
  updateItem: (proposalId: number, itemId: number, data: ProposalItemInput) =>
    api.put(`/api/proposals/${proposalId}/items/${itemId}`, data),
  removeItem: (proposalId: number, itemId: number) =>
    api.delete(`/api/proposals/${proposalId}/items/${itemId}`),

  // ---- PDF async flow ----
  generatePdf: (proposalId: number) =>
    api.post<{ job_id: number; status: string }>(`/api/proposals/${proposalId}/pdf/generate`),
  getPdfStatus: (proposalId: number) =>
    api.get<{ status: string; download_url?: string; error?: string }>(`/api/proposals/${proposalId}/pdf/status`),
}
