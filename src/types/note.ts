export interface Note {
  id: number
  title: string
  content: string           // markdown
  color?: 'yellow' | 'blue' | 'green' | 'pink' | 'gray'
  pinned: boolean
  tags: string[]
  client_id?: number
  created_at: string
  updated_at: string
}
