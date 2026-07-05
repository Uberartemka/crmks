import { ref } from 'vue'

/**
 * Shared state for the chat side panel: open/close.
 *
 * The chat is a slide-out panel (ChatPanel.vue), NOT a route — so the sidebar
 * entry needs to toggle it rather than navigate. Module-scoped state makes a
 * single source of truth that both AppSidebar (the "Чат" entry, like the
 * Воркспейс link) and WorkspaceLayout (which mounts <ChatPanel>) can read and
 * mutate. Same singleton pattern as useConfirm.
 */
const isOpen = ref(false)

export function useChatPanel() {
  function open() {
    isOpen.value = true
  }
  function close() {
    isOpen.value = false
  }
  function toggle() {
    isOpen.value = !isOpen.value
  }
  return { isOpen, open, close, toggle }
}
