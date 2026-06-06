export type ChatRole = 'user' | 'assistant' | 'tool' | 'system'

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolResult {
  tool_call_id: string
  content: string           // JSON-строка результата
}

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  tool_calls?: ToolCall[]
  tool_call_id?: string     // для role='tool'
  created_at: string
}

/** Описание инструмента в формате OpenAI/DeepSeek function calling */
export interface ToolDefinition {
  type: 'function'
  function: {
    name: string
    description: string
    parameters: {
      type: 'object'
      properties: Record<string, unknown>
      required?: string[]
    }
  }
}
