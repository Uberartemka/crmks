import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ChatPanel from './ChatPanel.vue'
import { useChatStore } from '@/stores/chat'

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

// Mock filesApi (eager upload при отправке сообщения с вложением)
// VAC 2.1.2 НЕ имеет события @upload-file — файлы приходят внутри send-message
// как массив объектов {blob,name,size,type,...}. onSend загружает их через
// filesApi.upload (восстанавливая File из blob) и передаёт attachment_id в store.
vi.mock('@/api/files', () => ({
  filesApi: {
    upload: vi.fn().mockResolvedValue({ data: { id: 77, original_name: 'x.pdf', mime_type: 'application/pdf', size_bytes: 1, is_image: false, url: '/api/files/77', thumbnail_url: null } }),
  },
}))

describe('ChatPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
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

  it('onSend с files вызывает filesApi.upload и шлёт attachment_id', async () => {
    // VAC 2.1.2: события @upload-file НЕТ. Файлы приходят внутри send-message
    // как detail[0].files — массив объектов {blob,name,size,type,...} (НЕ raw File).
    // onSend восстанавливает File из blob, грузит через filesApi.upload и передаёт
    // полученный id как attachment_id в store.sendMessage.
    const { filesApi } = await import('@/api/files')
    const { useChatStore } = await import('@/stores/chat')
    const sendMessageSpy = vi.spyOn(useChatStore(), 'sendMessage')

    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    // Реальная форма объекта file из VAC onFileChange (см. dist line 32198).
    const blob = new Blob(['x'], { type: 'application/pdf' })
    ;(wrapper.vm as any).onSend({
      detail: [
        {
          content: 'hi',
          roomId: 2,
          files: [{ blob, name: 'doc.pdf', type: 'application/pdf', size: 1, extension: 'pdf' }],
        },
      ],
    })
    await flushPromises()
    // File восстановлен из blob: проверяем имя и тип, а не identity.
    expect(filesApi.upload).toHaveBeenCalledWith(expect.any(File))
    const uploaded = (filesApi.upload as any).mock.calls[0][0] as File
    expect(uploaded.name).toBe('doc.pdf')
    expect(uploaded.type).toBe('application/pdf')
    // attachment_id из мока (id: 77) передан в store.sendMessage.
    expect(sendMessageSpy).toHaveBeenCalledWith(2, 'hi', undefined, 77)
  })

  it('onSend с files без blob — сообщение уходит БЕЗ attachment (не битый файл)', async () => {
    const { filesApi } = await import('@/api/files')
    const sendMessageSpy = vi.spyOn(useChatStore(), 'sendMessage')
    const wrapper = mount(ChatPanel, { global: globalStubs })
    await flushPromises()
    // VAC file entry without a populated blob (race / large file mid-fetch).
    ;(wrapper.vm as any).onSend({
      detail: [{
        content: 'hi',
        roomId: 2,
        files: [{ name: 'doc.pdf', type: 'application/pdf', size: 5, /* blob missing */ }],
      }],
    })
    await flushPromises()
    // upload must NOT be called (no junk "undefined" file uploaded)
    expect(filesApi.upload).not.toHaveBeenCalled()
    // message still sends, without an attachment_id
    expect(sendMessageSpy).toHaveBeenCalledWith(2, 'hi', undefined, undefined)
  })
})
