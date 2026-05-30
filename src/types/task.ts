export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked'
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'

export interface UserTask {
  id: number
  title: string
  description?: string
  status: TaskStatus
  priority: TaskPriority
  due_date?: string         // ISO
  assignee_id?: number
  client_id?: number        // привязка к клиенту (для менеджера)
  tags: string[]
  created_at: string
  updated_at: string
}
