<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import { Hash, Users, Megaphone } from 'lucide-vue-next'
import { computed } from 'vue'

const store = useChatStore()
const icon = (type: string) => type === 'general' ? Megaphone : type === 'department' ? Hash : Users
</script>

<template>
  <aside class="w-64 border-r border-slate-200 bg-white flex flex-col">
    <div class="p-4 border-b border-slate-200">
      <h2 class="font-bold text-lg">Чаты</h2>
    </div>
    <nav class="flex-1 overflow-y-auto py-2">
      <button
        v-for="c in store.channels"
        :key="c.id"
        class="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-slate-50 transition"
        :class="{ 'bg-brand-50 text-brand-700': c.id === store.activeChannelId }"
        @click="store.setActive(c.id)"
      >
        <component :is="icon(c.type)" :size="16" />
        <span class="flex-1 truncate text-sm">{{ c.name }}</span>
        <BaseBadge v-if="store.unread[c.id]" type="danger">{{ store.unread[c.id] }}</BaseBadge>
      </button>
    </nav>
  </aside>
</template>
