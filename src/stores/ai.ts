import { defineStore } from 'pinia'
import { ref } from 'vue'
import { nanoid } from '@/lib/nanoid'
import { aiApi } from '@/api/ai'
import type { ChatMessage } from '@/types/ai'

export const useAIStore = defineStore('ai', () => {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)

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
      const { data } = await aiApi.chat({
        messages: messages.value,
        tools: [],
      })

      const assistant = data.message
      messages.value.push(assistant)
    } finally {
      loading.value = false
    }
  }

  function reset() {
    messages.value = []
  }

  return { messages, loading, send, reset }
})
