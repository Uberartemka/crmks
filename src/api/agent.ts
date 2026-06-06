import { api } from './client'

export type LeadStatus = string

export interface ParseLeadsInput {
  query: string
  source?: string
  limit?: number
}

export interface ParsedLeadPreview {
  id: number
  name: string
  category?: string | null
  city?: string | null
  contacts?: string | null
  need_description?: string | null
  query?: string | null
  region?: string | null
  status?: LeadStatus
}

export interface ParseLeadsResponse {
  parsed: number
  created: number
  skipped: number
  leads: ParsedLeadPreview[]
  message?: string
}

export const agentApi = {
  parseLeads: (input: ParseLeadsInput) =>
    api.post<ParseLeadsResponse>('/api/agent/parse-leads', {
      query: input.query,
      source: input.source ?? '2gis',
      limit: input.limit ?? 20,
    }),
}
