export interface Proposal {
  id: number
  client_id: number
  client_name?: string
  title: string
  total_amount: number
  discount_global: number
  status: string
  email_sent: boolean
  created_at: string
  seq_num: number
  items?: ProposalItem[]
}

export interface ProposalItem {
  id: number
  sku_id: number
  sku: string
  type: string
  brand: string
  qty: number
  price_base: number
  discount_item: number
  price_final: number
}

export interface ProposalInput {
  client_id: number
  title?: string
  discount_global?: number
}

export interface ProposalItemInput {
  sku_id: number
  qty?: number
  discount_item?: number
}

export interface DiscountInput {
  discount_global: number
}

export interface SendEmailInput {
  recipient_email?: string
  subject?: string
}
