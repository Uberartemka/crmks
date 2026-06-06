export interface EmployeePlan {
  id: number
  user_id: number
  user_name?: string
  month: number
  year: number
  calls_target: number
  registrations_target: number
}

export interface PlanCreate {
  user_id: number
  month: number
  year: number
  calls_target?: number
  registrations_target?: number
}

export interface DailyPlanItem {
  user_id: number
  user_name: string
  calls_target: number
  daily_calls: number
  assigned_leads: number
  completed_calls: number
  remaining_calls: number
}
