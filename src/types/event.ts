export type EventKind = 'meeting' | 'call' | 'deadline' | 'reminder'

export interface CalendarEvent {
  id: number
  title: string
  description?: string
  kind: EventKind
  start: string             // ISO с временем
  end?: string              // ISO, если нет — точечное событие
  all_day: boolean
  location?: string
  client_id?: number
  participants?: string[]   // email'ы
  color?: 'blue' | 'green' | 'orange' | 'red' | 'purple'
  created_at: string
  updated_at: string
}

/** Унифицированный item на сетке: либо событие, либо задача с due_date */
export interface CalendarItem {
  id: string                // 'event-123' | 'task-456'
  source: 'event' | 'task'
  ref_id: number
  title: string
  start: Date
  end?: Date
  all_day: boolean
  color: string
  kind?: EventKind
}
