export type Role = 'admin' | 'manager' | 'client' | 'employee'

export interface User {
  id: number
  username: string
  name: string
  role: Role
  avatar_file_id?: number | null
  avatar_url?: string | null
}

export interface AuthState {
  user: User | null
  token: string | null
}
