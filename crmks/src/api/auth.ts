import { api } from './client'
import type { User } from '@/types/auth'

export const authApi = {
  login: (username: string, password: string) =>
    api.post<{ token: string; user: User }>('/api/auth/login', { username, password }),
  me: () => api.get<User>('/api/auth/me'),
  logout: () => api.post('/api/auth/logout'),
}
