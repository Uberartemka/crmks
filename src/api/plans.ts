import { api } from './client'
import type { EmployeePlan, PlanCreate, DailyPlanItem } from '@/types/plan'

export const plansApi = {
  list: () => api.get<EmployeePlan[]>('/api/plans'),
  create: (data: PlanCreate) => api.post<EmployeePlan>('/api/plans', data),
  daily: () => api.get<DailyPlanItem[]>('/api/daily-plan'),
}
