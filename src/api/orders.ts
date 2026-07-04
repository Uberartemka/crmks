import { api } from './client'
import type { Order } from '@/types/order'

export const ordersApi = {
  list: (params?: { client_id?: number }) => api.get<Order[]>('/api/orders', { params }),
  create: (data: Partial<Order>) => api.post<Order>('/api/orders', data),
  update: (id: number, data: Partial<Order>) => api.patch<Order>(`/api/orders/${id}`, data),
  remove: (id: number) => api.delete(`/api/orders/${id}`),
}
