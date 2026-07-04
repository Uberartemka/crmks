<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import TypingIndicator from './TypingIndicator.vue'

const store = useChatStore()
const props = defineProps<{ currentUserId: number }>()

// ⚠️ SPEC: content rendered ONLY via {{ }}, NEVER v-html (XSS protection).
// Line breaks via CSS white-space: pre-wrap, not <br> interpolation.
</script>

<template>
  <div class="flex-1 overflow-y-auto p-4 space-y-2 bg-slate-50">
    <div
      v-for="m in store.activeMessages"
      :key="m.id"
      class="flex"
      :class="{ 'justify-end': m.author_id === props.currentUserId }"
    >
      <div
        class="max-w-[70%] rounded-2xl px-4 py-2"
        :class="m.author_id === props.currentUserId
          ? 'bg-brand-600 text-white'
          : 'bg-white border border-slate-200'"
      >
        <p v-if="m.deleted_at" class="italic opacity-60">сообщение удалено</p>
        <p v-else class="text-sm" style="white-space: pre-wrap">{{ m.content }}</p>
        <span v-if="m.edited_at" class="text-[10px] opacity-50">(ред.)</span>
      </div>
    </div>
    <TypingIndicator :channel-id="store.activeChannelId ?? 0" />
  </div>
</template>
