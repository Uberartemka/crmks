<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/sidebar/AppSidebar.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()
const chatOpen = ref(false)

// Чат-панель доступна только staff (не клиентам) — клиенты чат не видят.
const isStaff = computed(() => Boolean(auth.role) && auth.role !== 'client')

// FAB-кнопка видна на дашбордах (как раньше AI), только для staff.
const showChatFab = computed(() => isStaff.value && route.path.endsWith('/dashboard'))

function openChat() {
  chatOpen.value = true
}

function closeChat() {
  chatOpen.value = false
}
</script>

<template>
  <div class="flex h-full">
    <AppSidebar />

    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>

    <ChatPanel v-if="isStaff" v-show="chatOpen" @close="closeChat" />

    <button
      v-if="!chatOpen && showChatFab"
      class="fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full bg-brand-600 text-white px-4 py-2 shadow-lg border border-black/10 hover:bg-brand-700"
      @click="openChat"
      title="Открыть чат команды"
    >
      <span class="text-sm font-semibold">Чат</span>
    </button>
  </div>
</template>
