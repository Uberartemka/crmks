export interface CallLog {
  id: number
  user_id: number
  user_name?: string
  client_id?: number | null
  lead_id?: number | null
  client_name: string
  from_number?: string
  to_number?: string
  direction?: string
  call_date: string
  status: string
  duration?: number
  recording_url?: string
  notes: string
  is_new_registration: boolean
  bitrix_call_id?: string
  created_at?: string
  updated_at?: string
}

export interface CallLogCreate {
  client_id?: number | null
  lead_id?: number | null
  client_name: string
  from_number?: string
  to_number?: string
  direction?: string
  call_date: string
  status?: string
  duration?: number
  recording_url?: string
  notes?: string
  is_new_registration?: boolean
  bitrix_call_id?: string
}
