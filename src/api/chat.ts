import { api } from './client'
import type { Channel, ChatMessage } from '@/types/chat'

export const chatApi = {
  listChannels: () => api.get<Channel[]>('/api/chat/channels'),
  createTopic: (data: { name: string; member_ids?: number[] }) =>
    api.post<Channel>('/api/chat/channels', { name: data.name, type: 'topic', member_ids: data.member_ids ?? [] }),
  listMessages: (channelId: number, before?: number) =>
    api.get<ChatMessage[]>(`/api/chat/channels/${channelId}/messages`, { params: before ? { before } : {} }),
  sendMessage: (channelId: number, data: { content: string; reply_to_id?: number | null }) =>
    api.post<ChatMessage>(`/api/chat/channels/${channelId}/messages`, data),
  editMessage: (id: number, content: string) =>
    api.patch<{ ok: boolean }>(`/api/chat/messages/${id}`, { content }),
  deleteMessage: (id: number) => api.delete(`/api/chat/messages/${id}`),
  markRead: (channelId: number) => api.post(`/api/chat/channels/${channelId}/read`),
  unread: () => api.get<Record<string, number>>('/api/chat/unread'),
  addMember: (channelId: number, userId: number) =>
    api.post(`/api/chat/channels/${channelId}/members`, { user_id: userId }),
  removeMember: (channelId: number, userId: number) =>
    api.delete(`/api/chat/channels/${channelId}/members/${userId}`),
  wsTicket: () => api.post<{ ticket: string }>('/api/chat/ws-ticket'),
}
