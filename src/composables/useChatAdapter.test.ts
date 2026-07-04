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
})
