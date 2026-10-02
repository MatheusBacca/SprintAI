import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import TerminalDock from '@/components/workspace/TerminalDock.vue'
import { isInside, resetTerminalBuffers, useTerminalsStore } from '@/stores/terminals'

vi.mock('@/components/workspace/TerminalPane.vue', () => ({
  __esModule: true,
  default: { name: 'TerminalPane', props: ['session', 'active'], template: '<div class="pane-stub" :data-active="active" />' },
}))

const encoder = new TextEncoder()

function json(body, status = 200) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

const NO_CONTENT = { ok: true, status: 204, headers: new Headers(), json: async () => null, text: async () => '' }

/** Stream que entrega os pedaços e fica parado (conexão viva). */
function streamOf(chunks) {
  let index = 0
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'text/event-stream' }),
    body: {
      getReader: () => ({
        read: async () => (index < chunks.length ? { done: false, value: encoder.encode(chunks[index++]) } : new Promise(() => {})),
        cancel: async () => {},
      }),
    },
  }
}

const sse = (data) => `event: ${data.type}\ndata: ${JSON.stringify(data)}\n\n`

function session(id, cwd, extra = {}) {
  return { id, profile: 'powershell', label: cwd.split('\\').pop(), cwd, cols: 120, rows: 30, created_at: '2026-10-02T12:00:00Z', alive: true, exit_code: null, offset: 0, ...extra }
}

const A = 'a'.repeat(16)
const B = 'b'.repeat(16)

beforeEach(() => {
  setActivePinia(createPinia())
  resetTerminalBuffers()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('stores/terminals', () => {
  it('reset e out escrevem no xterm, e o que chega repetido pela reconexão não duplica', () => {
    const store = useTerminalsStore()
    const writer = { write: vi.fn(), reset: vi.fn() }
    store._handle({ type: 'hello', sessions: [session(A, 'C:\\projects\\monitoria')] })
    store.attach(A, writer)
    expect(writer.reset).toHaveBeenCalledWith('')

    store._handle({ type: 'reset', s: A, o: 0, d: 'PS> ' })
    store._handle({ type: 'out', s: A, o: 4, d: 'dir\r\n' })
    // A reconexão manda de novo um pedaço que já chegou, com um final novo.
    store._handle({ type: 'out', s: A, o: 4, d: 'dir\r\nok' })
    store._handle({ type: 'out', s: A, o: 0, d: 'PS> ' })

    expect(writer.reset).toHaveBeenLastCalledWith('PS> ')
    expect(writer.write.mock.calls.map((c) => c[0])).toEqual(['dir\r\n', 'ok'])
    expect(store._since()).toBe(`${A}:11`)

    // Painel montado depois recebe o que já passou.
    const late = { write: vi.fn(), reset: vi.fn() }
    store.attach(A, late)
    expect(late.reset).toHaveBeenCalledWith('PS> dir\r\nok')
  })

  it('exit marca a sessão como encerrada e closed tira da lista', () => {
    const store = useTerminalsStore()
    store._handle({ type: 'hello', sessions: [session(A, 'C:\\projects\\monitoria'), session(B, 'C:\\projects\\qualificai')] })
    store._handle({ type: 'exit', s: A, code: 1 })
    expect(store.byId[A]).toMatchObject({ alive: false, exit_code: 1 })
    store._handle({ type: 'closed', s: B })
    expect(store.sessions.map((s) => s.id)).toEqual([A])
  })

  it('teclas de uma rajada vão num POST só, e a próxima rajada espera a anterior', async () => {
    vi.useFakeTimers()
    const posts = []
    let release
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init) => {
        posts.push(JSON.parse(init.body).data)
        if (posts.length === 1) await new Promise((resolve) => (release = resolve))
        return NO_CONTENT
      }),
    )
    const store = useTerminalsStore()
    store.input(A, 'g')
    store.input(A, 'i')
    store.input(A, 't')
    await vi.advanceTimersByTimeAsync(20)
    expect(posts).toEqual(['git'])

    store.input(A, ' status')
    store.input(A, '\r')
    await vi.advanceTimersByTimeAsync(50)
    expect(posts).toEqual(['git'])
    release()
    await vi.advanceTimersByTimeAsync(20)
    expect(posts).toEqual(['git', ' status\r'])
  })

  it('o stream manda o header da guarda e, ao reconectar, o since de cada sessão', async () => {
    const urls = []
    const responses = [
      streamOf([sse({ type: 'hello', sessions: [session(A, 'C:\\projects\\monitoria')] }), sse({ type: 'reset', s: A, o: 0, d: 'PS> ' })]),
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init) => {
        urls.push({ url, header: init.headers['X-SprintAI'] })
        return responses.shift() ?? streamOf([])
      }),
    )
    const store = useTerminalsStore()
    store.acquire()
    await flushPromises()
    expect(urls[0]).toEqual({ url: '/api/terminal/stream', header: '1' })
    expect(store.connected).toBe(true)
    expect(store.sessions.map((s) => s.id)).toEqual([A])

    store.release()
    store.acquire()
    await flushPromises()
    expect(urls.at(-1).url).toBe(`/api/terminal/stream?since=${encodeURIComponent(`${A}:4`)}`)
    store.release()
  })

  it('pasta do repo vale para a sessão aberta numa subpasta, e não para um vizinho de nome parecido', () => {
    expect(isInside('C:\\projects\\monitoria\\.claude\\worktrees\\WAI-8878', 'C:\\projects\\monitoria')).toBe(true)
    expect(isInside('c:\\Projects\\Monitoria', 'C:\\projects\\monitoria\\')).toBe(true)
    expect(isInside('C:\\projects\\monitoria-web', 'C:\\projects\\monitoria')).toBe(false)
  })
})

describe('TerminalDock', () => {
  let calls
  let health

  const repos = [
    { slug: 'monitoria', path: 'C:\\projects\\monitoria' },
    { slug: 'qualificai', path: 'C:\\projects\\qualificai' },
  ]
  const allRepos = [...repos, { slug: 'supervisor-web', path: 'C:\\projects\\supervisor-web' }]

  beforeEach(() => {
    calls = []
    health = true
    let created = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init = {}) => {
        const method = init.method ?? 'GET'
        const body = init.body ? JSON.parse(init.body) : undefined
        calls.push({ method, url, body })
        if (url === '/api/terminal/health') return health ? json({ ok: true, sessions: 0 }) : json({ detail: 'fora' }, 502)
        if (url.startsWith('/api/terminal/stream')) return streamOf([sse({ type: 'hello', sessions: [] })])
        if (url === '/api/terminal/sessions' && method === 'POST') {
          created += 1
          return json(session(String(created).repeat(16).slice(0, 16), body.cwd, { label: body.label }), 201)
        }
        if (method === 'DELETE') return NO_CONTENT
        throw new Error(`não mockado: ${method} ${url}`)
      }),
    )
  })

  async function mountDock(props = {}) {
    const wrapper = mount(TerminalDock, { props: { repos, allRepos, selectedRepo: 'monitoria', ...props } })
    await flushPromises()
    return wrapper
  }

  it('sem terminal host oferece o Windows Terminal', async () => {
    health = false
    const wrapper = await mountDock()
    expect(wrapper.find('.dock__empty').text()).toContain('não está no ar (porta 8766)')
    await wrapper.find('.dock__empty .btn').trigger('click')
    expect(wrapper.emitted('open-folder')).toEqual([['terminal', 'C:\\projects\\monitoria']])
    expect(calls.some((c) => c.url.startsWith('/api/terminal/stream'))).toBe(false)
  })

  it('abre um terminal na pasta do repo e mostra só as sessões dos repos do workspace', async () => {
    const wrapper = await mountDock()
    const store = useTerminalsStore()
    store._handle({ type: 'opened', session: session(B, 'C:\\projects\\weaction-api') })

    await wrapper.findAll('.dock__starters .btn')[0].trigger('click')
    await flushPromises()
    expect(calls).toContainEqual({
      method: 'POST',
      url: '/api/terminal/sessions',
      body: { cwd: 'C:\\projects\\monitoria', label: 'monitoria', cols: 120, rows: 30, profile: 'powershell' },
    })
    const panes = wrapper.findAll('.term')
    expect(panes).toHaveLength(1)
    expect(panes[0].find('.term__label').text()).toBe('monitoria')
    expect(panes[0].find('.term__state').text()).toBe('Ativo')

    await panes[0].find('.term__action[aria-label="Fechar terminal"]').trigger('click')
    await flushPromises()
    expect(calls.at(-1).method).toBe('DELETE')
    expect(wrapper.findAll('.term')).toHaveLength(0)
  })

  it('terminal em outro repo fixa o repo no workspace e abre nele', async () => {
    const wrapper = await mountDock()
    await wrapper.find('.dock__other').setValue('supervisor-web')
    await flushPromises()
    expect(wrapper.emitted('pin-repo')).toEqual([['supervisor-web']])
    expect(calls.find((c) => c.method === 'POST').body.cwd).toBe('C:\\projects\\supervisor-web')
  })

  it('mais de três terminais viram abas', async () => {
    const wrapper = await mountDock()
    const store = useTerminalsStore()
    for (const [i, slug] of ['monitoria', 'qualificai', 'monitoria', 'qualificai'].entries()) {
      store._handle({ type: 'opened', session: session(String(i).repeat(16), `C:\\projects\\${slug}`) })
    }
    await flushPromises()
    expect(wrapper.findAll('.dock__tab')).toHaveLength(4)
    expect(wrapper.findAll('.pane-stub[data-active="true"]')).toHaveLength(1)
  })
})
