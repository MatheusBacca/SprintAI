import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useRealtimeStore } from '@/stores/realtime'

const encoder = new TextEncoder()

/** Resposta de stream que entrega os pedaços na ordem e depois fecha. */
function streamOf(chunks, { hold = false } = {}) {
  let index = 0
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'text/event-stream' }),
    body: {
      getReader: () => ({
        read: async () => {
          if (index < chunks.length) return { done: false, value: encoder.encode(chunks[index++]) }
          // `hold` simula a conexão viva e parada (o caso real entre eventos).
          if (hold) return new Promise(() => {})
          return { done: true, value: undefined }
        },
        cancel: async () => {},
      }),
    },
  }
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

describe('stores/realtime', () => {
  it('lê o stream com o header da guarda e conta cada evento por tipo', async () => {
    const fetchMock = vi.fn(async () =>
      streamOf(
        [
          ': conectado\n\n',
          'event: activity.new\ndata: {"source": "jira", "count": 3}\n\n',
          'event: note.changed\ndata: {"id": 7}\n\nevent: activity.new\ndata: {"count": 1}\n\n',
        ],
        { hold: true },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const realtime = useRealtimeStore()
    realtime.connect()
    await flush()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/events')
    expect(init.headers['X-SprintAI']).toBe('1')

    expect(realtime.connected).toBe(true)
    expect(realtime.revisionOf('activity.new')).toBe(2)
    expect(realtime.revisionOf('note.changed')).toBe(1)
    expect(realtime.events['activity.new'].payload).toEqual({ count: 1 })
    expect(realtime.revisionOf('nunca.aconteceu')).toBe(0)

    realtime.disconnect()
    expect(realtime.connected).toBe(false)
  })

  it('evento partido entre dois pedaços é remontado', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        streamOf(['event: sync.fi', 'nished\ndata: {"id":', ' 12, "status": "success"}\n\n'], { hold: true }),
      ),
    )

    const realtime = useRealtimeStore()
    realtime.connect()
    await flush()

    expect(realtime.revisionOf('sync.finished')).toBe(1)
    expect(realtime.events['sync.finished'].payload.id).toBe(12)
    realtime.disconnect()
  })

  it('comentário de keepalive não vira evento', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => streamOf([': ping\n\n', ': ping\n\n'], { hold: true })))

    const realtime = useRealtimeStore()
    realtime.connect()
    await flush()

    expect(realtime.events).toEqual({})
    expect(realtime.connected).toBe(true)
    realtime.disconnect()
  })

  it('API fora do ar deixa a tela sem stream e agenda nova tentativa', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(async () => ({ ok: false, status: 503, body: null }))
    vi.stubGlobal('fetch', fetchMock)

    const realtime = useRealtimeStore()
    realtime.connect()
    await vi.advanceTimersByTimeAsync(0)

    expect(realtime.connected).toBe(false)
    expect(realtime.error).toContain('503')

    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchMock.mock.calls.length).toBeGreaterThan(1)

    realtime.disconnect()
    vi.useRealTimers()
  })

  it('conectar duas vezes não abre dois streams', async () => {
    const fetchMock = vi.fn(async () => streamOf([': conectado\n\n'], { hold: true }))
    vi.stubGlobal('fetch', fetchMock)

    const realtime = useRealtimeStore()
    realtime.connect()
    realtime.connect()
    await flush()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    realtime.disconnect()
  })
})
