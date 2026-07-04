export type OrderStatus =
  | 'new'
  | 'confirmed'
  | 'paid'
  | 'shipped'
  | 'delivered'
  | 'cancelled'

export interface Order {
  id: number
  client_id: number
  created_by?: number
  order_number?: string
  name: string
  qty: number
  total: number
  status: OrderStatus
  order_date?: string
  created_at: string
  updated_at: string
}
