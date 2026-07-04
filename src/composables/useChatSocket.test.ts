import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useChatSocket } from './useChatSocket'

class MockWS {
  static instances: MockWS[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []
  constructor(url: string) { this.url = url; MockWS.instances.push(this) }
  send(data: string) { this.sent.push(data) }
  close() { this.onclose?.() }
}

describe('useChatSocket', () => {
  beforeEach(() => {
    MockWS.instances = []
    ;(globalThis as any).WebSocket = MockWS
  })
  afterEach(() => { delete (globalThis as any).WebSocket })

  it('connects with ticket and marks ready on open', () => {
    const { connect, isReady } = useChatSocket()
    connect('ws://x', 'T123')
    expect(MockWS.instances[0].url).toBe('ws://x?ticket=T123')
    MockWS.instances[0].onopen?.()
    expect(isReady.value).toBe(true)
  })

  it('dispatches incoming message to handler', () => {
    const received: any[] = []
    const { connect, onMessage } = useChatSocket()
    onMessage((m) => received.push(m))
    connect('ws://x', 'T1')
    MockWS.instances[0].onmessage?.({ data: JSON.stringify({ type: 'message', message: { id: 1 } }) })
    expect(received).toHaveLength(1)
    expect(received[0].type).toBe('message')
  })
})
