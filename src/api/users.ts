import { api } from './client'

export interface UserOut {
  id: number
  username: string
  name: string
  role: string
  client_id?: number | null
  client_name?: string | null
  avatar_url?: string | null
  avatar_file_id?: number | null
}

export const usersApi = {
  list: () => api.get<UserOut[]>('/api/users'),
  create: (data: {
    username: string
    password: string
    name: string
    role?: string
    client_id?: number | null
  }) => api.post<UserOut>('/api/users', data),
  delete: (id: number) => api.delete(`/api/users/${id}`),
}
