<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import { computed } from 'vue'

const props = defineProps<{ channelId: number }>()
const store = useChatStore()
const show = computed(() => (store.typingUsers[props.channelId]?.length ?? 0) > 0)
</script>

<template>
  <p v-if="show" class="text-xs text-slate-400 px-2">печатает…</p>
</template>
