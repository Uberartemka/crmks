<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useChatSocket } from '@/composables/useChatSocket'
import { chatApi } from '@/api/chat'
import ChannelList from '@/components/chat/ChannelList.vue'
import MessageList from '@/components/chat/MessageList.vue'
import MessageInput from '@/components/chat/MessageInput.vue'

const store = useChatStore()
const auth = useAuthStore()
const { connect, onMessage } = useChatSocket()

const wsBase = import.meta.env.DEV
  ? 'ws://localhost:8000/ws/chat'
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/chat`

onMounted(async () => {
  await store.loadChannels()
  await store.loadUnread()
  if (store.activeChannelId) await store.loadHistory(store.activeChannelId)

  // connect WS with a fresh ticket
  const { data } = await chatApi.wsTicket()
  connect(wsBase, data.ticket)
  onMessage((msg) => {
    if (msg.type === 'message') store.onIncomingMessage(msg.message)
    else if (msg.type === 'unread') store.onUnread(msg.channel_id)
    else if (msg.type === 'typing') store.onTyping(msg.channel_id, msg.user_id)
  })
})

const me = computed(() => auth.user?.id ?? 0)
</script>

<template>
  <div class="flex h-full">
    <ChannelList />
    <section v-if="store.activeChannel" class="flex-1 flex flex-col">
      <header class="px-4 py-3 border-b border-slate-200 bg-white">
        <h1 class="font-bold">{{ store.activeChannel.name }}</h1>
      </header>
      <MessageList :current-user-id="me" />
      <MessageInput />
    </section>
    <section v-else class="flex-1 flex items-center justify-center text-slate-400">
      Выберите канал
    </section>
  </div>
</template>
