import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPanel from './ChatPanel.vue'

// Stub vue-advanced-chat (web component — не монтируем настоящий)
// и CreateChannelModal (не нужен для unit-теста)
const globalStubs = {
  stubs: {
    'vue-advanced-chat': { template: '<div class="vac-stub" />' },
    CreateChannelModal: { template: '<div />' },
  },
}

// Mock useChatSocket (возвращает пустые функции, чтобы onMounted не падал)
vi.mock('@/composables/useChatSocket', () => ({
  useChatSocket: () => ({
    connect: vi.fn(),
    onMessage: vi.fn(),
  }),
}))

// Mock chatApi (не делаем реальных запросов)
vi.mock('@/api/chat', () => ({
  chatApi: {
    wsTicket: vi.fn().mockResolvedValue({ data: { ticket: 'test-ticket' } }),
    listChannels: vi.fn().mockResolvedValue({ data: [] }),
    listMessages: vi.fn().mockResolvedValue({ data: [] }),
    unread: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

describe('ChatPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('монтируется и рендерит header "Чат команды"', async () => {
    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    expect(wrapper.text()).toContain('Чат команды')
  })

  it('эмитит close при клике на кнопку X', async () => {
    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    const closeBtn = wrapper.find('button[title="Закрыть"]')
    expect(closeBtn.exists()).toBe(true)
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
    expect(wrapper.emitted('close')!.length).toBe(1)
  })
})
