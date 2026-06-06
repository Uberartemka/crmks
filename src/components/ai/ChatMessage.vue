<script setup lang="ts">
import type { ChatMessage } from '@/types/ai'
import { marked } from 'marked'
import { computed, ref, watch, onUnmounted } from 'vue'

const props = defineProps<{ msg: ChatMessage }>()
const displayedContent = ref('')
let typingInterval: number | null = null

// Typing speed in milliseconds per character
const TYPING_SPEED = 15

// Check if this message should have typing effect
const shouldType = computed(() => props.msg.role === 'assistant')

// Parse markdown of displayed content
const html = computed(() => {
  if (!displayedContent.value) return ''
  return marked.parse(displayedContent.value, { async: false }) as string
})

const bubble = computed(() => {
  switch (props.msg.role) {
    case 'user': return 'bg-brand-600 text-white ml-auto'
    case 'assistant': return 'bg-white border border-slate-200'
    case 'tool': return 'bg-slate-100 text-slate-600 text-xs font-mono'
    default: return 'bg-slate-50'
  }
})

// Start typing effect when message content changes
watch(() => props.msg.content, (newContent) => {
  if (!newContent) {
    displayedContent.value = ''
    return
  }
  
  // For non-assistant messages or if already fully displayed, show immediately
  if (!shouldType.value || newContent.length <= displayedContent.value.length) {
    displayedContent.value = newContent
    return
  }
  
  // Clear any existing interval
  if (typingInterval) {
    clearInterval(typingInterval)
    typingInterval = null
  }
  
  // Start typing from current position
  const startIndex = displayedContent.value.length
  let index = startIndex
  
  typingInterval = window.setInterval(() => {
    if (index < newContent.length) {
      displayedContent.value += newContent[index]
      index++
    } else {
      if (typingInterval) {
        clearInterval(typingInterval)
        typingInterval = null
      }
    }
  }, TYPING_SPEED)
}, { immediate: true })

onUnmounted(() => {
  if (typingInterval) {
    clearInterval(typingInterval)
  }
})
</script>

<template>
  <div v-if="msg.role !== 'system'" class="flex">
    <div class="rounded-lg px-3 py-2 max-w-[85%]" :class="bubble">
      <div v-if="msg.role === 'tool'">
        🔧 tool result: <span class="break-all">{{ msg.content.slice(0, 200) }}</span>
      </div>
      <div v-else-if="msg.tool_calls?.length" class="text-xs italic text-slate-500">
        ⚙️ вызываю: {{ msg.tool_calls.map(c => c.name).join(', ') }}
      </div>
      <div v-else class="prose prose-sm max-w-none" v-html="html" />
    </div>
  </div>
</template>
