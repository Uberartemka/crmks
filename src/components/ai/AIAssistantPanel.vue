<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useAIStore } from '@/stores/ai'
import ChatMessage from './ChatMessage.vue'
import QuickActions from './QuickActions.vue'
import { Send, Sparkles, Trash2 } from 'lucide-vue-next'

const ai = useAIStore()
const text = ref('')
const scrollEl = ref<HTMLElement | null>(null)

async function send() {
  const v = text.value.trim()
  if (!v || ai.loading) return
  text.value = ''
  await ai.send(v)
}

watch(() => ai.messages.length, async () => {
  await nextTick()
  scrollEl.value?.scrollTo({ top: scrollEl.value.scrollHeight, behavior: 'smooth' })
})
</script>

<template>
  <aside class="flex flex-col h-full bg-slate-50 border-l border-slate-200 w-[360px] shrink-0">
    <header class="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-white">
      <div class="flex items-center gap-2">
        <Sparkles :size="16" class="text-brand-600" />
        <h3 class="font-semibold text-sm">AI ассистент</h3>
      </div>
      <button class="btn-ghost !p-1" @click="ai.reset" title="Очистить">
        <Trash2 :size="14" />
      </button>
    </header>

    <div ref="scrollEl" class="flex-1 overflow-y-auto p-3 space-y-2">
      <p v-if="!ai.messages.length" class="text-xs text-slate-500 text-center py-6">
        Я могу создавать задачи, заметки, готовить документы.<br>
        Просто напиши что нужно.
      </p>
      <ChatMessage v-for="m in ai.messages" :key="m.id" :msg="m" />
      <div v-if="ai.loading" class="text-xs text-slate-500 italic">думаю…</div>
    </div>

    <QuickActions />

    <div class="p-2 border-t border-slate-200 bg-white">
      <div class="flex gap-2">
        <textarea
          v-model="text"
          rows="2"
          class="input resize-none"
          placeholder="Спроси что-нибудь..."
          @keydown.enter.exact.prevent="send"
        />
        <button class="btn-primary" :disabled="ai.loading" @click="send">
          <Send :size="16" />
        </button>
      </div>
    </div>
  </aside>
</template>
