<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import BaseButton from '@/components/ui/BaseButton.vue'
import { Send } from 'lucide-vue-next'

const store = useChatStore()
const text = ref('')

async function submit() {
  const content = text.value.trim()
  if (!content || !store.activeChannelId) return
  text.value = ''
  await store.sendMessage(store.activeChannelId, content)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="border-t border-slate-200 bg-white p-3 flex items-end gap-2">
    <textarea
      v-model="text"
      class="input flex-1 resize-none"
      rows="1"
      maxlength="10000"
      placeholder="Написать сообщение…"
      @keydown="onKey"
    />
    <BaseButton variant="primary" :disabled="!text.trim()" @click="submit">
      <Send :size="16" />
    </BaseButton>
  </div>
</template>
