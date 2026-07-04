import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { chatApi } from '@/api/chat'
import type { Channel, ChatMessage } from '@/types/chat'

export const useChatStore = defineStore('chat', () => {
  const channels = ref<Channel[]>([])
  const activeChannelId = ref<number | null>(null)
  const messagesByChannel = ref<Record<number, ChatMessage[]>>({})
  const unread = ref<Record<number, number>>({})
  const loading = ref(false)
  const typingUsers = ref<Record<number, number[]>>({})  // channelId -> user_ids typing

  const activeChannel = computed(() =>
    channels.value.find((c) => c.id === activeChannelId.value) ?? null,
  )
  const activeMessages = computed(() =>
    activeChannelId.value ? messagesByChannel.value[activeChannelId.value] ?? [] : [],
  )

  async function loadChannels() {
    loading.value = true
    try {
      const { data } = await chatApi.listChannels()
      channels.value = data
      if (!activeChannelId.value && data.length) activeChannelId.value = data[0].id
    } finally {
      loading.value = false
    }
  }

  async function loadUnread() {
    const { data } = await chatApi.unread()
    unread.value = data
  }

  async function loadHistory(channelId: number, before?: number) {
    const { data } = await chatApi.listMessages(channelId, before)
    // newest first from API; reverse for display (oldest at top)
    const ordered = [...data].reverse()
    if (before) {
      // older page — prepend
      messagesByChannel.value[channelId] = [...ordered, ...(messagesByChannel.value[channelId] ?? [])]
    } else {
      messagesByChannel.value[channelId] = ordered
    }
  }

  async function sendMessage(channelId: number, content: string) {
    const { data } = await chatApi.sendMessage(channelId, { content })
    // optimistic: append locally; WS will broadcast to others
    messagesByChannel.value[channelId] = [...(messagesByChannel.value[channelId] ?? []), data]
    // clear unread for self
    unread.value[channelId] = 0
  }

  async function markRead(channelId: number) {
    await chatApi.markRead(channelId)
    unread.value[channelId] = 0
  }

  // Called by useChatSocket when a WS 'message' frame arrives
  function onIncomingMessage(msg: ChatMessage) {
    const list = messagesByChannel.value[msg.channel_id] ?? []
    messagesByChannel.value[msg.channel_id] = [...list, msg]
    if (msg.channel_id !== activeChannelId.value) {
      unread.value[msg.channel_id] = (unread.value[msg.channel_id] ?? 0) + 1
    }
  }

  function onUnread(channelId: number) {
    if (channelId !== activeChannelId.value) {
      // refresh unread count from store best-effort (WS doesn't carry count)
      loadUnread()
    }
  }

  function onTyping(channelId: number, userId: number) {
    const cur = typingUsers.value[channelId] ?? []
    if (!cur.includes(userId)) typingUsers.value[channelId] = [...cur, userId]
  }

  function setActive(channelId: number) {
    activeChannelId.value = channelId
    unread.value[channelId] = 0
  }

  return {
    channels, activeChannelId, activeChannel, activeMessages,
    messagesByChannel, unread, typingUsers, loading,
    loadChannels, loadUnread, loadHistory, sendMessage, markRead,
    setActive, onIncomingMessage, onUnread, onTyping,
  }
})
