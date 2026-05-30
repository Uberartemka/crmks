<script setup lang="ts">
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import AIAssistantPanel from '@/components/ai/AIAssistantPanel.vue'
</script>

<template>
  <div class="flex h-full">
    <AppSidebar />
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
    <AIAssistantPanel />
  </div>
</template>
