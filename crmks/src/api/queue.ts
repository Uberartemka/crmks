import { api } from './client'

export interface QueueTaskInput {
  task_type: '1c_sync' | 'crm_lead' | 'email_invoice'
  payload: Record<string, unknown>
  max_retries?: number
}

export const queueApi = {
  add: (data: QueueTaskInput) => api.post('/api/queue/add', data),
  list: () => api.get('/api/queue/list'),
  stats: () => api.get('/api/queue/stats'),
  status: (id: number) => api.get(`/api/queue/status/${id}`),
  retry: (id: number) => api.post(`/api/queue/retry/${id}`),
}
