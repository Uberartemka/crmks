<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useChatSocket } from '@/composables/useChatSocket'
import { chatApi } from '@/api/chat'
import { toRoom, toMessage } from '@/composables/useChatAdapter'
import CreateChannelModal from '@/components/chat/CreateChannelModal.vue'

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
  // replyMessage comes from vue-advanced-chat's reply slot (set by onReply);
  // its _id is the message id we forward as reply_to_id.
  const replyToId = replyMessage?._id ? Number(replyMessage._id) : undefined
  store.sendMessage(Number(roomId), content, replyToId)
}

function onReply(_event: any) {
  // vue-advanced-chat handles the reply UX itself: it places the selected
  // message into a reply-slot above the input with a cancel button. We don't
  // need to manage state here — on send, the replyMessage payload is passed
  // back via the send-message event (handled in onSend).
}

async function onFetch(event: any) {
  const { room, options } = event.detail[0]
  const channelId = Number(room.roomId)
  messagesLoaded.value = false
  if (options?.reset) {
    store.setActive(channelId)
    await store.loadHistory(channelId)
  } else {
    // cursor: oldest loaded message id
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
  <div class="h-full">
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
      lang="ru"
      height="100%"
      @send-message="onSend"
      @fetch-messages="onFetch"
      @add-room="openCreateModal"
      @message-reply="onReply"
    />
    <CreateChannelModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @created="onChannelCreated"
    />
  </div>
</template>
