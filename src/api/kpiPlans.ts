import { api } from './client'

export interface KpiPlansManagerDailyDetail {
  date: string
  visits: number
  messenger: number
  leads: number
  calls: number
  used_units: number
  capacity_pct: number
  is_past: boolean
}

export interface KpiPlansManager {
  user_id: number
  user_name: string
  base_plan_units: number
  adjusted_plan_units: number
  work_days: string[]
  passed_days: number
  fact_cum: Array<number | null>
  plan_cum: number[]
  daily_details: KpiPlansManagerDailyDetail[]
  stats: {
    completion_pct: number
    cap_today_pct: number
    leads_month_total: number
    visits_month_total: number
    calls_month_total: number
    messenger_month_total: number
    delta_units: number
  }
}

export interface KpiPlansPayload {
  year: number
  month: number
  work_days_count: number
  managers: KpiPlansManager[]
}

export const kpiPlansApi = {
  get: (params: { month: number; year: number }) => api.get<KpiPlansPayload>('/api/kpi-plans', { params }),
}
