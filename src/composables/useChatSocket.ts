import { ref } from 'vue'

type IncomingHandler = (msg: any) => void

/**
 * Singleton-ish WebSocket manager for chat. One connection per app lifetime,
 * mounted in App.vue's <script setup>. Auth uses a single-use ticket fetched
 * via REST (POST /api/chat/ws-ticket with the Bearer token), then passed as
 * ?ticket= to the WS URL — never the raw token in the URL.
 *
 * ⚠️ XSS note (spec): content from WS/REST is rendered ONLY via {{ }} in
 * MessageList.vue, never v-html.
 */
export function useChatSocket() {
  const isReady = ref(false)
  let ws: WebSocket | null = null
  const handlers: IncomingHandler[] = []

  function connect(baseWsUrl: string, ticket: string) {
    ws = new WebSocket(`${baseWsUrl}?ticket=${ticket}`)
    ws.onopen = () => { isReady.value = true }
    ws.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data)
        handlers.forEach((h) => h(msg))
      } catch {
        // ignore non-JSON frames
      }
    }
    ws.onclose = () => { isReady.value = false }
  }

  function onMessage(h: IncomingHandler) {
    handlers.push(h)
  }

  function send(payload: object) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload))
    }
  }

  function close() {
    ws?.close()
    ws = null
  }

  return { isReady, connect, onMessage, send, close }
}
