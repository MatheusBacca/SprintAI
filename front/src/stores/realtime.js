import { defineStore } from 'pinia'
import { API_BASE, CLIENT_HEADER } from '@/services/api'

/**
 * Stream de eventos da API local (B11).
 *
 * Não dá para usar `EventSource`: ele não manda header nenhum, e a guarda local exige
 * `X-SprintAI`. Então lemos o `text/event-stream` com `fetch` + `ReadableStream` e
 * fazemos o parse aqui — a guarda continua inteira.
 *
 * Cada tipo de evento vira um contador em `events`; as telas observam o contador que
 * lhes interessa e recarregam. O polling do `sync.js` fica de rede de segurança.
 */
const RETRY_MS = [1000, 2000, 5000, 10_000, 30_000]

function parseBlock(block) {
  let kind = 'message'
  const data = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue // comentário/keepalive
    if (line.startsWith('event:')) kind = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }
  if (!data.length) return null
  try {
    return { kind, payload: JSON.parse(data.join('\n')) }
  } catch {
    return { kind, payload: {} }
  }
}

export const useRealtimeStore = defineStore('realtime', {
  state: () => ({
    connected: false,
    error: null,
    /** `{ 'activity.new': { count, at, payload } }` — o contador é o gatilho dos watchers. */
    events: {},
    _controller: null,
    _stopped: true,
    _attempt: 0,
  }),
  getters: {
    // Contadores separados: uma tela que só liga para lembrete não recarrega por sync.
    revisionOf: (state) => (kind) => state.events[kind]?.count ?? 0,
  },
  actions: {
    connect() {
      if (!this._stopped) return
      this._stopped = false
      this._loop()
    },

    disconnect() {
      this._stopped = true
      this._controller?.abort()
      this._controller = null
      this.connected = false
    },

    record(kind, payload) {
      const previous = this.events[kind]?.count ?? 0
      this.events = { ...this.events, [kind]: { count: previous + 1, at: Date.now(), payload } }
    },

    async _loop() {
      while (!this._stopped) {
        try {
          await this._read()
          this._attempt = 0
        } catch (error) {
          if (this._stopped) return
          this.connected = false
          this.error = error?.message ?? String(error)
        }
        if (this._stopped) return
        const wait = RETRY_MS[Math.min(this._attempt++, RETRY_MS.length - 1)]
        await new Promise((resolve) => setTimeout(resolve, wait))
      }
    },

    async _read() {
      const controller = new AbortController()
      this._controller = controller
      const response = await fetch(`${API_BASE}/events`, {
        headers: { [CLIENT_HEADER]: '1', Accept: 'text/event-stream' },
        signal: controller.signal,
      })
      if (!response.ok || !response.body) throw new Error(`Stream indisponível (${response.status})`)

      this.connected = true
      this.error = null
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const blocks = buffer.split('\n\n')
          buffer = blocks.pop() ?? ''
          for (const block of blocks) {
            const event = parseBlock(block)
            if (event) this.record(event.kind, event.payload)
          }
        }
      } finally {
        this.connected = false
        reader.cancel().catch(() => {})
      }
    },
  },
})
