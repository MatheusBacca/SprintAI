import { defineStore } from 'pinia'
import { CLIENT_HEADER, request } from '@/services/api'
import { parseBlock } from '@/stores/realtime'

/**
 * Terminais do Workspace (F15) — clientes do terminal host (`back/terminal_host.py`).
 *
 * - **Um stream para todas as sessões** (`/api/terminal/stream`), lido com `fetch` +
 *   `ReadableStream` como o `/api/events`: o navegador abre no máximo seis conexões por
 *   origem, e um stream por terminal as esgotaria.
 * - **Saída numerada.** Cada sessão guarda até onde já chegou (`offset`); a reconexão manda
 *   o `since` e recebe só o que falta — ou um `reset` com o buffer inteiro, se ficou para
 *   trás dele. Recarregar a página reata os shells vivos.
 * - **Teclas agrupadas e em ordem.** O que é digitado dentro de ~12 ms vai num POST só, e o
 *   próximo POST da mesma sessão só sai depois do anterior.
 *
 * O texto dos terminais fica fora do estado reativo (Maps do módulo): é muito, muda a cada
 * tecla, e só o xterm precisa dele.
 */
const RETRY_MS = [500, 1000, 2000, 5000, 10_000]
const INPUT_DELAY_MS = 12
const RESIZE_DELAY_MS = 120
const BUFFER_CHARS = 200_000

const offsets = new Map()
const buffers = new Map()
const writers = new Map()
const inputs = new Map()
const resizes = new Map()

function terminalPath(path) {
  return `/terminal${path}`
}

function sameFolder(a, b) {
  const norm = (p) => (p ?? '').replace(/[\\/]+$/, '').toLowerCase()
  return norm(a) === norm(b)
}

export function isInside(path, folder) {
  const norm = (p) => (p ?? '').replace(/[\\/]+$/, '').toLowerCase()
  const inner = norm(path)
  const outer = norm(folder)
  return inner === outer || inner.startsWith(`${outer}\\`) || inner.startsWith(`${outer}/`)
}

export const useTerminalsStore = defineStore('terminals', {
  state: () => ({
    sessions: [],
    /** `null` = ainda não perguntou; `false` = terminal host fora do ar. */
    available: null,
    connected: false,
    error: null,
    opening: false,
    _users: 0,
    _controller: null,
    _attempt: 0,
  }),
  getters: {
    byId: (state) => Object.fromEntries(state.sessions.map((s) => [s.id, s])),
  },
  actions: {
    async checkHealth() {
      try {
        await request(terminalPath('/health'))
        this.available = true
      } catch {
        this.available = false
      }
      return this.available
    },

    /** Quem mostra terminal pede o stream; o último a sair fecha. */
    acquire() {
      this._users += 1
      if (this._users === 1) this._loop()
    },

    release() {
      this._users = Math.max(0, this._users - 1)
      if (this._users === 0) {
        this._controller?.abort()
        this._controller = null
        this.connected = false
      }
    },

    async open({ cwd, label = null, cols = 120, rows = 30 }) {
      this.opening = true
      this.error = null
      try {
        const session = await request(terminalPath('/sessions'), {
          method: 'POST',
          body: { cwd, label, cols, rows, profile: 'powershell' },
        })
        this._upsert(session)
        return session
      } catch (error) {
        this.error = error.message
        return null
      } finally {
        this.opening = false
      }
    },

    async close(id) {
      try {
        await request(terminalPath(`/sessions/${id}`), { method: 'DELETE' })
      } catch (error) {
        if (error.status !== 404) this.error = error.message
      }
      this._forget(id)
    },

    /** Fecha a sessão encerrada e abre outra na mesma pasta. */
    async reopen(id) {
      const old = this.byId[id]
      if (!old) return null
      await this.close(id)
      return this.open({ cwd: old.cwd, label: old.label, cols: old.cols, rows: old.rows })
    },

    sessionsIn(folders) {
      return this.sessions.filter((s) => folders.some((folder) => isInside(s.cwd, folder)))
    },

    sessionFor(folder) {
      return this.sessions.find((s) => sameFolder(s.cwd, folder) && s.alive) ?? null
    },

    // --- Saída para o xterm -------------------------------------------------------------

    /** O painel do terminal se registra; recebe na hora o que já chegou. */
    attach(id, writer) {
      writers.set(id, writer)
      const buffer = buffers.get(id)
      writer.reset(buffer ?? '')
    },

    detach(id, writer) {
      if (writers.get(id) === writer) writers.delete(id)
    },

    // --- Entrada --------------------------------------------------------------------------

    input(id, data) {
      const entry = inputs.get(id) ?? { queue: '', timer: null, sending: false }
      entry.queue += data
      inputs.set(id, entry)
      if (!entry.timer && !entry.sending) entry.timer = setTimeout(() => this._flushInput(id), INPUT_DELAY_MS)
    },

    async _flushInput(id) {
      const entry = inputs.get(id)
      if (!entry) return
      entry.timer = null
      if (!entry.queue) return
      const data = entry.queue
      entry.queue = ''
      entry.sending = true
      try {
        await request(terminalPath(`/sessions/${id}/input`), { method: 'POST', body: { data } })
      } catch (error) {
        if (error.status === 404) this._forget(id)
        else this.error = error.message
      } finally {
        entry.sending = false
        if (entry.queue) this._flushInput(id)
      }
    },

    resize(id, cols, rows) {
      clearTimeout(resizes.get(id))
      resizes.set(
        id,
        setTimeout(async () => {
          const session = this.byId[id]
          if (!session || (session.cols === cols && session.rows === rows)) return
          session.cols = cols
          session.rows = rows
          try {
            await request(terminalPath(`/sessions/${id}/resize`), { method: 'POST', body: { cols, rows } })
          } catch {
            // Tamanho perdido se acerta no próximo redimensionamento.
          }
        }, RESIZE_DELAY_MS),
      )
    },

    // --- Stream ---------------------------------------------------------------------------

    async _loop() {
      while (this._users > 0) {
        try {
          await this._read()
          this._attempt = 0
        } catch (error) {
          if (this._users === 0) return
          this.connected = false
          this.error = error?.name === 'AbortError' ? null : error?.message ?? String(error)
          if (this.available !== false) await this.checkHealth()
        }
        if (this._users === 0) return
        const wait = RETRY_MS[Math.min(this._attempt++, RETRY_MS.length - 1)]
        await new Promise((resolve) => setTimeout(resolve, wait))
      }
    },

    _since() {
      return [...offsets.entries()].map(([id, offset]) => `${id}:${offset}`).join(',')
    },

    async _read() {
      const controller = new AbortController()
      this._controller = controller
      const since = this._since()
      const query = since ? `?since=${encodeURIComponent(since)}` : ''
      const response = await fetch(`/api/terminal/stream${query}`, {
        headers: { [CLIENT_HEADER]: '1', Accept: 'text/event-stream' },
        signal: controller.signal,
      })
      if (!response.ok || !response.body) throw new Error(`Terminal indisponível (${response.status})`)

      this.connected = true
      this.available = true
      this.error = null
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let pending = ''
      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          pending += decoder.decode(value, { stream: true })
          const blocks = pending.split('\n\n')
          pending = blocks.pop() ?? ''
          for (const block of blocks) {
            const event = parseBlock(block)
            if (event) this._handle(event.payload)
          }
        }
      } finally {
        this.connected = false
        reader.cancel().catch(() => {})
      }
    },

    _handle(frame) {
      switch (frame.type) {
        case 'hello': {
          const alive = new Set(frame.sessions.map((s) => s.id))
          for (const id of [...offsets.keys()]) if (!alive.has(id)) this._forget(id)
          this.sessions = frame.sessions
          break
        }
        case 'opened':
          this._upsert(frame.session)
          break
        case 'closed':
          this._forget(frame.s)
          break
        case 'exit': {
          const session = this.byId[frame.s]
          if (session) {
            session.alive = false
            session.exit_code = frame.code
          }
          break
        }
        case 'reset':
          buffers.set(frame.s, frame.d.slice(-BUFFER_CHARS))
          offsets.set(frame.s, frame.o + frame.d.length)
          writers.get(frame.s)?.reset(frame.d)
          break
        case 'out':
          this._append(frame.s, frame.o, frame.d)
          break
        default:
          // `resync`: o stream acaba logo depois e a reconexão manda o `since`.
          break
      }
    },

    _append(id, offset, data) {
      const known = offsets.get(id) ?? 0
      if (offset + data.length <= known) return
      const text = offset < known ? data.slice(known - offset) : data
      offsets.set(id, offset + data.length)
      const buffer = (buffers.get(id) ?? '') + text
      buffers.set(id, buffer.length > BUFFER_CHARS ? buffer.slice(-BUFFER_CHARS) : buffer)
      writers.get(id)?.write(text)
    },

    _upsert(session) {
      const index = this.sessions.findIndex((s) => s.id === session.id)
      if (index === -1) this.sessions = [...this.sessions, session]
      else this.sessions.splice(index, 1, { ...this.sessions[index], ...session })
    },

    _forget(id) {
      this.sessions = this.sessions.filter((s) => s.id !== id)
      offsets.delete(id)
      buffers.delete(id)
      writers.delete(id)
      inputs.delete(id)
      clearTimeout(resizes.get(id))
      resizes.delete(id)
    },
  },
})

/** Só para os testes: zera o que mora fora do estado do Pinia. */
export function resetTerminalBuffers() {
  for (const map of [offsets, buffers, writers, inputs, resizes]) map.clear()
}
