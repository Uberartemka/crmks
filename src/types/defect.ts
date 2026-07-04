export type DefectStatus = 'new' | 'critical' | 'replacement_ordered' | 'resolved'

export interface Defect {
  id: number
  client_id: number
  created_by?: number
  equipment: string
  bearing?: string
  description: string
  status: DefectStatus
  action?: string
  detected_at?: string
  created_at: string
  updated_at: string
}
