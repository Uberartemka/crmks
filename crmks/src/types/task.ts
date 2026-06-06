export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked'
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'

export interface UserTask {
  id: number
  title: string
  description?: string
  status: TaskStatus
  priority: TaskPriority
  due_date?: string // ISO
  estimated_minutes?: number
  assignee_id?: number
  assignee_name?: string // имя ответственного
  client_id?: number // привязка к клиенту (для менеджера)
  call_id?: number // привязка к звонку (call_logs.id)
  tags: string[]
  created_at: string
  updated_at: string
}
