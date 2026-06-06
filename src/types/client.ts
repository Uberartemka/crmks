export interface Client {
  id: number
  name: string
  bitrix_id?: string
  email?: string
  city?: string
  discount: number
  status: string
}

export interface ClientCreate {
  name: string
  email?: string
  city?: string
  bitrix_id?: string
  discount?: number
}
