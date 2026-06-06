import { api } from './client'
import type { ChatMessage, ToolDefinition, ToolResult } from '@/types/ai'

export const aiApi = {
  /** Прокси к Kimi (Moonshot AI) с tool calling.
   *  Бэк сам управляет tools и agent loop. */
  chat: (payload: {
    messages: ChatMessage[]
    tools?: ToolDefinition[]
    tool_results?: ToolResult[]
  }) => api.post<{ message: ChatMessage }>('/api/ai/chat', payload),
}
