export type ChannelType = 'general' | 'department' | 'topic'

export interface Channel {
  id: number
  name: string
  type: ChannelType
  department_role?: string | null
  archived?: boolean
}

export interface ChatMessage {
  id: number
  channel_id: number
  author_id: number
  content: string
  reply_to_id?: number | null
  created_at: string | null
  edited_at?: string | null
  deleted_at?: string | null
}

export interface WsTicket {
  ticket: string
  expires_in: number
}
