<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import AIAssistantPanel from '@/components/ai/AIAssistantPanel.vue'

const route = useRoute()
const isAiOpen = ref(false)

// The floating AI button lives in the bottom-right corner and collides with
// controls on working screens (e.g. it visually blocks the chat send button on
// /chat, covers action bars on tables). Keep it only on dashboards — the AI
// assistant belongs on the "home" screen, not on every working surface. All
// dashboard routes end with '/dashboard' (admin/manager/employee/client).
const showAiFab = computed(() => route.path.endsWith('/dashboard'))

function openAi() {
  isAiOpen.value = true
}

function closeAi() {
  isAiOpen.value = false
}
</script>

<template>
  <div class="flex h-full">
    <AppSidebar />

    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>

    <div class="h-full" v-show="isAiOpen">
      <AIAssistantPanel @close="closeAi" />
    </div>

    <button
      v-if="!isAiOpen && showAiFab"
      class="fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full bg-brand-600 text-white px-4 py-2 shadow-lg border border-black/10 hover:bg-brand-700"
      @click="openAi"
      title="Открыть AI ассистента"
    >
      <span class="text-sm font-semibold">AI</span>
      <span aria-hidden="true">✨</span>
    </button>
  </div>
</template>
