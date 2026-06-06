<script setup lang="ts">
import { ref } from 'vue'
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import AIAssistantPanel from '@/components/ai/AIAssistantPanel.vue'

const isAiOpen = ref(false)

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
      v-if="!isAiOpen"
      class="fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full bg-brand-600 text-white px-4 py-2 shadow-lg border border-black/10 hover:bg-brand-700"
      @click="openAi"
      title="Открыть AI ассистента"
    >
      <span class="text-sm font-semibold">AI</span>
      <span aria-hidden="true">✨</span>
    </button>
  </div>
</template>
