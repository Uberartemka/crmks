import { api } from './client'
import type { ChatMessage, ToolDefinition, ToolResult } from '@/types/ai'

export const aiApi = {
  /** Прокси к DeepSeek с function calling.
   *  Бэк сам передаёт tools и возвращает либо контент, либо tool_calls. */
  chat: (payload: {
    messages: ChatMessage[]
    tools: ToolDefinition[]
    tool_results?: ToolResult[]
  }) => api.post<{ message: ChatMessage }>('/api/ai/chat', payload),
}
