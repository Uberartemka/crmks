import { api } from './client'
import type { CalendarEvent } from '@/types/event'

export const eventsApi = {
  list: (params?: { from?: string; to?: string }) =>
    api.get<CalendarEvent[]>('/api/events', { params }),
  create: (data: Partial<CalendarEvent>) => api.post<CalendarEvent>('/api/events', data),
  update: (id: number, data: Partial<CalendarEvent>) =>
    api.patch<CalendarEvent>(`/api/events/${id}`, data),
  remove: (id: number) => api.delete(`/api/events/${id}`),
}
