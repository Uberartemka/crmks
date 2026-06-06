export type Role = 'admin' | 'manager' | 'client' | 'employee'

export interface User {
  id: number
  username: string
  name: string
  role: Role
}

export interface AuthState {
  user: User | null
  token: string | null
}
