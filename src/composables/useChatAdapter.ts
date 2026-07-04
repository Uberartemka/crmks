import type { Channel, ChatMessage } from '@/types/chat'

// Our Channel now has members[] (backend returns it). Add it to the type.
interface ChannelWithMembers extends Channel {
  members?: { id: number; username: string; name: string }[]
}

interface VACRoom {
  roomId: string
  roomName: string
  unreadCount: number
  users: { _id: string; username: string }[]
}

interface VACMessage {
  _id: string
  content: string
  senderId: string
  username: string
  date: string
  timestamp: string
  saved: boolean
  distributed: boolean
  seen: boolean
  // pass-through for reply support
  replyMessage?: { _id: string; content: string; senderId: string } | null
}

export function toRoom(c: ChannelWithMembers, unread: number): VACRoom {
  return {
    roomId: String(c.id),
    roomName: c.name,
    unreadCount: unread,
    users: (c.members ?? []).map((m) => ({ _id: String(m.id), username: m.name })),
  }
}

export function toMessage(
  m: ChatMessage & { author_username?: string | null; author_name?: string | null },
): VACMessage {
  const created = m.created_at ? new Date(m.created_at) : null
  return {
    _id: String(m.id),
    content: m.deleted_at ? 'сообщение удалено' : m.content,
    senderId: String(m.author_id),
    username: m.author_name ?? m.author_username ?? 'Неизвестно',
    date: created ? created.toLocaleDateString('ru-RU') : '',
    timestamp: created
      ? created.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
      : '',
    saved: true,
    distributed: true,
    seen: false,
    replyMessage: m.reply_to_id
      ? { _id: String(m.reply_to_id), content: '', senderId: '' }
      : null,
  }
}
