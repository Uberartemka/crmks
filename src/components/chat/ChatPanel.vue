<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useChatSocket } from '@/composables/useChatSocket'
import { chatApi } from '@/api/chat'
import { toRoom, toMessage } from '@/composables/useChatAdapter'
import CreateChannelModal from '@/components/chat/CreateChannelModal.vue'
import { X } from 'lucide-vue-next'

const emit = defineEmits<{ close: [] }>()

const store = useChatStore()
const auth = useAuthStore()
const { connect, onMessage } = useChatSocket()

const messagesLoaded = ref(true)
const showCreateModal = ref(false)

const currentUserId = computed(() => String(auth.user?.id ?? 0))
const rooms = computed(() =>
  store.channels.map((c) => toRoom(c as any, store.unread[c.id] ?? 0)),
)
const messages = computed(() => store.activeMessages.map((m) => toMessage(m as any)))
const canCreate = computed(() => auth.role === 'admin' || auth.role === 'manager')

// Имя отправителя видно при ≥2 участников (вместо дефолта VAC ≥3).
// currentUser:false — своё собственное имя не показываем.
const usernameOptions = { minUsers: 2, currentUser: false }

const wsBase = import.meta.env.DEV
  ? 'ws://localhost:8000/ws/chat'
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/chat`

onMounted(async () => {
  await store.loadChannels()
  await store.loadUnread()
  if (store.activeChannelId) {
    await store.loadHistory(store.activeChannelId)
    messagesLoaded.value = true
  }
  try {
    const { data } = await chatApi.wsTicket()
    connect(wsBase, data.ticket)
    onMessage((msg) => {
      if (msg.type === 'message') store.onIncomingMessage(msg.message)
      else if (msg.type === 'unread') store.onUnread(msg.channel_id)
      else if (msg.type === 'typing') store.onTyping(msg.channel_id, msg.user_id)
    })
  } catch (e) {
    console.warn('chat WS connect failed', e)
  }
})

function onSend(event: any) {
  const { content, roomId, replyMessage } = event.detail[0]
  const replyToId = replyMessage?._id ? Number(replyMessage._id) : undefined
  store.sendMessage(Number(roomId), content, replyToId)
}

function onReply(_event: any) {
  // vue-advanced-chat handles the reply UX itself; replyMessage comes back in onSend.
}

async function onFetch(event: any) {
  const { room, options } = event.detail[0]
  const channelId = Number(room.roomId)
  messagesLoaded.value = false
  if (options?.reset) {
    store.setActive(channelId)
    await store.loadHistory(channelId)
  } else {
    const msgs = store.messagesByChannel[channelId] ?? []
    const before = msgs.length ? msgs[0].id : undefined
    await store.loadHistory(channelId, before)
  }
  messagesLoaded.value = true
}

function openCreateModal() {
  showCreateModal.value = true
}

async function onChannelCreated() {
  showCreateModal.value = false
  await store.loadChannels()
  await store.loadUnread()
}
</script>

<template>
  <aside class="chat-pattern-bg flex flex-col h-full bg-slate-50 border-l-4 border-brand-500 shadow-2xl shrink-0 w-[720px]">
    <header class="flex items-center justify-between px-3 py-2 border-b border-slate-200 bg-white">
      <h3 class="font-semibold text-sm">Чат команды</h3>
      <button
        class="p-1 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-800 transition-colors"
        title="Закрыть"
        @click="emit('close')"
      >
        <X :size="14" />
      </button>
    </header>
    <div class="flex-1 overflow-hidden">
      <vue-advanced-chat
        :current-user-id="currentUserId"
        :rooms="rooms"
        :messages="messages"
        :rooms-loaded="true"
        :messages-loaded="messagesLoaded"
        :add-room-enabled="canCreate"
        :room-info-enabled="true"
        :show-search="false"
        :show-files="false"
        :show-audio="false"
        :textarea-action-enabled="false"
        :username-options="usernameOptions"
        :responsive-breakpoint="400"
        lang="ru"
        height="100%"
        @send-message="onSend"
        @fetch-messages="onFetch"
        @add-room="openCreateModal"
        @message-reply="onReply"
      />
    </div>
    <CreateChannelModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @created="onChannelCreated"
    />
  </aside>
</template>
