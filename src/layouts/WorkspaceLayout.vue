<script setup lang="ts">
import { computed } from 'vue'
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatPanel } from '@/composables/useChatPanel'

const auth = useAuthStore()
const { isOpen: chatOpen, close: closeChat } = useChatPanel()

// Чат-панель доступна только staff (не клиентам) — клиенты чат не видят.
const isStaff = computed(() => Boolean(auth.role) && auth.role !== 'client')
</script>

<template>
  <div class="flex h-full">
    <AppSidebar />

    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>

    <ChatPanel v-if="isStaff" v-show="chatOpen" @close="closeChat" />
  </div>
</template>
