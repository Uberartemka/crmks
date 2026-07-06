export type ChannelType = 'general' | 'department' | 'topic'

export interface Channel {
  id: number
  name: string
  type: ChannelType
  department_role?: string | null
  archived?: boolean
  members?: { id: number; username: string; name: string; avatar_url?: string | null; avatar_file_id?: number | null }[]
}

export interface ChatAttachment {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  is_image: boolean
  url: string // "/api/chat-attachments/{id}" — public, no auth
  thumbnail_url: string | null
}

export interface ChatMessage {
  id: number
  channel_id: number
  author_id: number
  content: string
  reply_to_id?: number | null
  reply_message?: {
    id: number
    content: string
    author_id: number | null
    author_name: string | null
  } | null
  attachment?: ChatAttachment | null
  created_at: string | null
  edited_at?: string | null
  deleted_at?: string | null
  author_username?: string | null
  author_name?: string | null
  avatar_url?: string | null
}

export interface WsTicket {
  ticket: string
  expires_in: number
}
