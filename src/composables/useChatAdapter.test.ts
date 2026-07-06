import { describe, it, expect } from 'vitest'
import { toMessage } from './useChatAdapter'

describe('toMessage', () => {
  it('maps reply_message into vue-advanced-chat replyMessage format', () => {
    const result = toMessage({
      id: 42,
      channel_id: 1,
      author_id: 7,
      content: 'hello',
      reply_to_id: 40,
      reply_message: {
        id: 40,
        content: 'original',
        author_id: 9,
        author_name: 'Анна',
      },
      created_at: null,
    } as any)
    expect(result.replyMessage).toEqual({
      _id: '40',
      content: 'original',
      senderId: '9',
      username: 'Анна',
    })
  })

  it('returns null replyMessage when reply_message is absent', () => {
    const result = toMessage({
      id: 42,
      channel_id: 1,
      author_id: 7,
      content: 'plain',
      reply_to_id: null,
      reply_message: null,
      created_at: null,
    } as any)
    expect(result.replyMessage).toBeNull()
  })

  it('maps attachment to a VAC file with previewUrl for images', () => {
    const result = toMessage({
      id: 1,
      channel_id: 1,
      author_id: 2,
      content: 'see photo',
      attachment: {
        id: 9,
        original_name: 'photo.png',
        mime_type: 'image/png',
        size_bytes: 1024,
        is_image: true,
        url: '/api/chat-attachments/9',
        thumbnail_url: '/api/chat-attachments/9/thumbnail',
      },
      created_at: null,
    } as any)
    expect(result.file).toEqual({
      name: 'photo.png',
      size: 1024,
      type: 'image/png',
      url: '/api/chat-attachments/9',
      previewUrl: '/api/chat-attachments/9/thumbnail',
    })
  })

  it('maps attachment to a VAC file without previewUrl for documents', () => {
    const result = toMessage({
      id: 1,
      channel_id: 1,
      author_id: 2,
      content: 'see pdf',
      attachment: {
        id: 10,
        original_name: 'Договор.pdf',
        mime_type: 'application/pdf',
        size_bytes: 9999,
        is_image: false,
        url: '/api/chat-attachments/10',
        thumbnail_url: null,
      },
      created_at: null,
    } as any)
    expect(result.file).toEqual({
      name: 'Договор.pdf',
      size: 9999,
      type: 'application/pdf',
      url: '/api/chat-attachments/10',
    })
    expect(result.file).not.toHaveProperty('previewUrl')
  })

  it('omits file when there is no attachment', () => {
    const result = toMessage({
      id: 1,
      channel_id: 1,
      author_id: 2,
      content: 'plain',
      created_at: null,
    } as any)
    expect(result.file).toBeUndefined()
  })
})
