import {
  startOfMonth, endOfMonth, startOfWeek, endOfWeek, addDays, addMonths, addWeeks,
  format, isSameDay, isSameMonth, isToday, eachDayOfInterval,
} from 'date-fns'
import { ru } from 'date-fns/locale'
import type { CalendarEvent, CalendarItem } from '@/types/event'
import type { UserTask } from '@/types/task'

export const RU_LOCALE = { locale: ru, weekStartsOn: 1 as const }

export function monthGridDays(anchor: Date): Date[] {
  // 6 недель x 7 дней — как в Frappe CRM (фикс. высота)
  const start = startOfWeek(startOfMonth(anchor), RU_LOCALE)
  const end = endOfWeek(endOfMonth(anchor), RU_LOCALE)
  return eachDayOfInterval({ start, end })
}

export function weekDays(anchor: Date): Date[] {
  const start = startOfWeek(anchor, RU_LOCALE)
  return eachDayOfInterval({ start, end: addDays(start, 6) })
}

export function dayHours(): number[] {
  return Array.from({ length: 24 }, (_, i) => i)
}

const KIND_COLOR: Record<NonNullable<CalendarEvent['color']>, { bg: string; dot: string; text: string }> = {
  blue:   { bg: 'bg-blue-100',    dot: 'bg-blue-500',    text: 'text-blue-800' },
  green:  { bg: 'bg-emerald-100', dot: 'bg-emerald-500', text: 'text-emerald-800' },
  orange: { bg: 'bg-orange-100',  dot: 'bg-orange-500',  text: 'text-orange-800' },
  red:    { bg: 'bg-red-100',     dot: 'bg-red-500',     text: 'text-red-800' },
  purple: { bg: 'bg-purple-100',  dot: 'bg-purple-500',  text: 'text-purple-800' },
}

export function colorClasses(c: CalendarEvent['color'] = 'blue') {
  return KIND_COLOR[c]
}

/** Сводим события + задачи (с due_date) в единый список items для сетки. */
export function buildItems(events: CalendarEvent[], tasks: UserTask[]): CalendarItem[] {
  const fromEvents: CalendarItem[] = events.map(e => ({
    id: `event-${e.id}`, source: 'event', ref_id: e.id, title: e.title,
    start: new Date(e.start), end: e.end ? new Date(e.end) : undefined,
    all_day: e.all_day, kind: e.kind, color: e.color ?? 'blue',
  }))
  const fromTasks: CalendarItem[] = tasks
    .filter((t): t is UserTask & { due_date: string } => !!t.due_date)
    .map(t => ({
      id: `task-${t.id}`, source: 'task', ref_id: t.id,
      title: `📋 ${t.title}`, start: new Date(t.due_date), all_day: true,
      color: t.priority === 'urgent' ? 'red' : t.priority === 'high' ? 'orange' : 'blue',
    }))
  return [...fromEvents, ...fromTasks].sort((a, b) => a.start.getTime() - b.start.getTime())
}

export function itemsOnDay(items: CalendarItem[], day: Date): CalendarItem[] {
  return items.filter(i => isSameDay(i.start, day))
}

export {
  startOfMonth, endOfMonth, startOfWeek, endOfWeek, addDays, addMonths, addWeeks,
  format, isSameDay, isSameMonth, isToday,
}
