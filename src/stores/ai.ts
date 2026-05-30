import { defineStore } from 'pinia'
import { ref } from 'vue'
import { nanoid } from '@/lib/nanoid'
import { aiApi } from '@/api/ai'
import type { ChatMessage, ToolCall, ToolResult, ToolDefinition } from '@/types/ai'
import { useTasksStore } from './tasks'
import { useNotesStore } from './notes'

/** Описание инструментов, доступных модели. */
const TOOLS: ToolDefinition[] = [
  {
    type: 'function',
    function: {
      name: 'create_task',
      description: 'Создать новую задачу в воркспейсе пользователя',
      parameters: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          description: { type: 'string' },
          priority: { type: 'string', enum: ['low', 'medium', 'high', 'urgent'] },
          due_date: { type: 'string', description: 'ISO 8601' },
        },
        required: ['title'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'create_note',
      description: 'Создать заметку',
      parameters: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          content: { type: 'string', description: 'markdown' },
          tags: { type: 'array', items: { type: 'string' } },
        },
        required: ['title', 'content'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'list_tasks',
      description: 'Получить список задач, опционально с фильтром по статусу',
      parameters: {
        type: 'object',
        properties: {
          status: { type: 'string', enum: ['todo', 'in_progress', 'done', 'blocked'] },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'update_task_status',
      description: 'Обновить статус задачи',
      parameters: {
        type: 'object',
        properties: {
          id: { type: 'number' },
          status: { type: 'string', enum: ['todo', 'in_progress', 'done', 'blocked'] },
        },
        required: ['id', 'status'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'prepare_document',
      description: 'Подготовить документ (ТЭО, КП, отчёт аудита). Возвращает URL/превью.',
      parameters: {
        type: 'object',
        properties: {
          kind: { type: 'string', enum: ['teo', 'kp', 'audit'] },
          client_id: { type: 'number' },
          params: { type: 'object', additionalProperties: true },
        },
        required: ['kind'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'create_event',
      description: 'Создать событие в календаре (встреча, звонок, дедлайн, напоминание)',
      parameters: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          kind: { type: 'string', enum: ['meeting', 'call', 'deadline', 'reminder'] },
          start: { type: 'string', description: 'ISO 8601 datetime' },
          end: { type: 'string', description: 'ISO 8601 datetime, optional' },
          all_day: { type: 'boolean' },
          location: { type: 'string' },
          description: { type: 'string' },
        },
        required: ['title', 'start'],
      },
    },
  },
]

/** Локальные обработчики tool-вызовов. */
async function executeTool(call: ToolCall): Promise<ToolResult> {
  const tasks = useTasksStore()
  const notes = useNotesStore()

  try {
    let result: unknown
    switch (call.name) {
      case 'create_task':
        result = await tasks.create(call.arguments as any)
        break
      case 'create_note':
        result = await notes.create(call.arguments as any)
        break
      case 'list_tasks':
        result = await tasks.list(call.arguments as any)
        break
      case 'update_task_status': {
        const { id, status } = call.arguments as { id: number; status: any }
        result = await tasks.update(id, { status })
        break
      }
      case 'prepare_document':
        result = { status: 'queued', preview_url: null, kind: (call.arguments as any).kind }
        break
      case 'create_event': {
        const { useEventsStore } = await import('./events')
        const ev = useEventsStore()
        result = await ev.create(call.arguments as any)
        break
      }
      default:
        result = { error: `unknown tool: ${call.name}` }
    }
    return { tool_call_id: call.id, content: JSON.stringify(result) }
  } catch (e: any) {
    return { tool_call_id: call.id, content: JSON.stringify({ error: e?.message ?? 'failed' }) }
  }
}

export const useAIStore = defineStore('ai', () => {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const MAX_TOOL_ROUNDS = 5

  async function send(userText: string) {
    const userMsg: ChatMessage = {
      id: nanoid(),
      role: 'user',
      content: userText,
      created_at: new Date().toISOString(),
    }
    messages.value.push(userMsg)
    loading.value = true

    try {
      let round = 0
      let toolResults: ToolResult[] = []

      while (round < MAX_TOOL_ROUNDS) {
        const { data } = await aiApi.chat({
          messages: messages.value,
          tools: TOOLS,
          tool_results: toolResults,
        })

        const assistant = data.message
        messages.value.push(assistant)

        if (!assistant.tool_calls?.length) break

        toolResults = await Promise.all(assistant.tool_calls.map(executeTool))

        for (const r of toolResults) {
          messages.value.push({
            id: nanoid(),
            role: 'tool',
            tool_call_id: r.tool_call_id,
            content: r.content,
            created_at: new Date().toISOString(),
          })
        }
        round++
      }
    } finally {
      loading.value = false
    }
  }

  function reset() {
    messages.value = []
  }

  return { messages, loading, send, reset }
})
