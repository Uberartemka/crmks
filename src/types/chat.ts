export type ChannelType = 'general' | 'department' | 'topic'

export interface Channel {
  id: number
  name: string
  type: ChannelType
  department_role?: string | null
  archived?: boolean
  members?: { id: number; username: string; name: string }[]
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
  created_at: string | null
  edited_at?: string | null
  deleted_at?: string | null
  author_username?: string | null
  author_name?: string | null
}

export interface WsTicket {
  ticket: string
  expires_in: number
}
