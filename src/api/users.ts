import { api } from './client'

export interface UserOut {
  id: number
  username: string
  name: string
  role: string
}

export const usersApi = {
  list: () => api.get<UserOut[]>('/api/users'),
  create: (data: { username: string; password: string; name: string; role?: string }) =>
    api.post<UserOut>('/api/users', data),
  delete: (id: number) => api.delete(`/api/users/${id}`),
}
