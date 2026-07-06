import type { Channel, ChatMessage } from '@/types/chat'

// Our Channel now has members[] (backend returns it). Add it to the type.
interface ChannelWithMembers extends Channel {
  members?: { id: number; username: string; name: string; avatar_url?: string | null; avatar_file_id?: number | null }[]
}

interface VACRoom {
  roomId: string
  roomName: string
  unreadCount: number
  users: { _id: string; username: string; avatar?: string }[]
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
  file?: {
    name: string
    size: number
    type: string
    url: string
    previewUrl?: string
  }
}

export function toRoom(c: ChannelWithMembers, unread: number): VACRoom {
  return {
    roomId: String(c.id),
    roomName: c.name,
    unreadCount: unread,
    users: (c.members ?? []).map((m) => ({
      _id: String(m.id),
      username: m.name,
      avatar: m.avatar_url ?? '',
    })),
  }
}

export function toMessage(
  m: ChatMessage & { author_username?: string | null; author_name?: string | null; avatar_url?: string | null },
): VACMessage {
  const created = m.created_at ? new Date(m.created_at) : null
  return {
    _id: String(m.id),
    content: m.deleted_at ? 'сообщение удалено' : m.content,
    senderId: String(m.author_id),
    username: m.author_name ?? m.author_username ?? 'Неизвестно',
    // vue-advanced-chat reads message.avatar (NOT users[].avatar) to render the
    // sender's picture next to the message. Without this, avatars never show
    // in the message list even if users[].avatar is set.
    avatar: m.avatar_url ?? '',
    date: created ? created.toLocaleDateString('ru-RU') : '',
    timestamp: created
      ? created.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
      : '',
    saved: true,
    distributed: true,
    seen: false,
    replyMessage: m.reply_message
      ? {
          _id: String(m.reply_message.id),
          content: m.reply_message.content,
          senderId: String(m.reply_message.author_id ?? ''),
          username: m.reply_message.author_name ?? 'Неизвестно',
        }
      : null,
    file: m.attachment
      ? {
          name: m.attachment.original_name,
          size: m.attachment.size_bytes,
          type: m.attachment.mime_type,
          url: m.attachment.url,
          ...(m.attachment.is_image && m.attachment.thumbnail_url
            ? { previewUrl: m.attachment.thumbnail_url }
            : {}),
        }
      : undefined,
  }
}
