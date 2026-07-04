<script setup lang="ts">
import { watchEffect } from 'vue'
import { RouterView } from 'vue-router'
import ConfirmModal from '@/components/ui/ConfirmModal.vue'
import { useAuthStore } from '@/stores/auth'

// Chat WS connection lives for the whole app, but only when authenticated
// and only for staff roles (clients don't see chat).
const auth = useAuthStore()
watchEffect(() => {
  if (auth.isAuthenticated && auth.role && auth.role !== 'client') {
    // lazily import so client-role users don't pull chat bundle
    import('@/composables/useChatSocket')
  }
})
</script>

<template>
  <RouterView />
  <ConfirmModal />
</template>
