<script setup lang="ts">
import type { ChatMessage } from '@/types/ai'
import { marked } from 'marked'
import { computed } from 'vue'

const props = defineProps<{ msg: ChatMessage }>()
const html = computed(() => marked.parse(props.msg.content || '', { async: false }) as string)

const bubble = computed(() => {
  switch (props.msg.role) {
    case 'user': return 'bg-brand-600 text-white ml-auto'
    case 'assistant': return 'bg-white border border-slate-200'
    case 'tool': return 'bg-slate-100 text-slate-600 text-xs font-mono'
    default: return 'bg-slate-50'
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
