import { api } from './client'

export interface ReportMetrics {
  period: string
  revenue: number
  order_count: number
  avg_check: number
  proposals_count: number
  delivered_count: number
  conversion: number
  dynamics: { labels: string[]; values: number[] }
}

export const reportsApi = {
  metrics: (period: string = 'month') =>
    api.get<ReportMetrics>('/api/reports/metrics', { params: { period } }),
}
