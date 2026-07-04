export type MachineryStatus = 'normal' | 'warning' | 'critical' | 'replaced'

export interface Machine {
  id: number
  client_id: number
  created_by?: number
  name: string
  node?: string
  bearing?: string
  brand?: string
  install_date?: string
  wear: number
  status: MachineryStatus
  created_at: string
  updated_at: string
}
