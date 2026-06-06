export interface Lead {
  id: number
  name: string
  category?: string
  city?: string
  contacts?: string
  need_description?: string
  query?: string
  region?: string
  status: string
  assigned_to?: number | null
  assigned_name?: string
  call_count: number
  created_at?: string
}

export interface LeadAssign {
  user_id?: number
}

export interface LeadStatusUpdate {
  status: string
}
