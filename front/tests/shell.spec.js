import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from '@/App.vue'
import { navItems, routes } from '@/router/routes'
import { useHealthStore } from '@/stores/health'
import { useRealtimeStore } from '@/stores/realtime'
import { useRefreshStore } from '@/stores/refresh'
import { useUiStore } from '@/stores/ui'

/**
 * Todo App montado aqui é desmontado no fim do teste, e as asserções leem os stores pelo
 * `pinia` dele, nunca pelo "ativo". Um App esquecido continua vivo — polling, stream, a view
 * da rota que termina de carregar depois — e todo `useStore()` dentro de um componente dele
 * reativa o pinia *dele*. Com a máquina carregada a view do teste anterior chegava atrasada,
 * e o `useUiStore()` do teste seguinte lia o tema de outro App (ou o evento de sync ia para
 * outra tela): dois testes falhavam de vez em quando na suíte cheia.
 */
const mounted = []

async function mountApp(path = '/') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(App, { global: { plugins: [router, pinia] } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router, pinia }
}

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
})

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ status: 'ok', version: '0.1.0', database: { status: 'up' } }),
    }),
  )
})

describe('app shell', () => {
  it('renderiza um item de navegação por rota navegável', async () => {
    const { wrapper } = await mountApp()

    const items = wrapper.findAll('.sidebar__item')
    expect(items).toHaveLength(navItems.length)
    expect(items.map((i) => i.text())).toEqual(navItems.map((r) => r.meta.title))
  })

  it('mostra o breadcrumb da rota', async () => {
    const { wrapper } = await mountApp('/semana')

    expect(wrapper.find('.topbar__crumb--current').text()).toBe('Semana')
  })

  it('reflete o health da API no indicador', async () => {
    const { wrapper, pinia } = await mountApp()

    expect(useHealthStore(pinia).level).toBe('ok')
    expect(wrapper.find('.topbar__status--ok').exists()).toBe(true)
  })
})

describe('health store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('fica degraded quando a API responde mas o banco está fora', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ status: 'degraded', version: '0.1.0', database: { status: 'down' } }),
    })
    const store = useHealthStore()

    await store.check()

    expect(store.level).toBe('degraded')
  })

  it('fica down quando a API não responde', async () => {
    fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const store = useHealthStore()

    await store.check()

    expect(store.level).toBe('down')
  })
})

describe('tema claro e escuro', () => {
  /**
   * O jsdom não implementa matchMedia; quem quiser testar a preferência do
   * sistema precisa fingi-la antes do store nascer.
   */
  function stubSystemTheme(dark) {
    const listeners = new Set()
    vi.stubGlobal('matchMedia', (query) => ({
      matches: dark && query.includes('dark'),
      media: query,
      addEventListener: (_, fn) => listeners.add(fn),
      removeEventListener: (_, fn) => listeners.delete(fn),
    }))
    return (next) => listeners.forEach((fn) => fn({ matches: next }))
  }

  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sem preferência salva, segue o tema escuro do sistema', async () => {
    stubSystemTheme(true)

    const { pinia } = await mountApp()

    expect(useUiStore(pinia).theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('o botão da sidebar alterna o tema e guarda a escolha', async () => {
    stubSystemTheme(false)
    const { wrapper, pinia } = await mountApp()
    const ui = useUiStore(pinia)

    await wrapper.find('.sidebar__theme').trigger('click')

    expect(ui.theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('sprintai.theme')).toBe('dark')

    await wrapper.find('.sidebar__theme').trigger('click')

    expect(ui.theme).toBe('light')
    expect(document.documentElement.dataset.theme).toBeUndefined()
    expect(localStorage.getItem('sprintai.theme')).toBe('light')
  })

  it('a escolha manual vence a preferência do sistema', async () => {
    localStorage.setItem('sprintai.theme', 'light')
    const emitSystemChange = stubSystemTheme(true)

    const { pinia } = await mountApp()
    const ui = useUiStore(pinia)
    expect(ui.theme).toBe('light')

    // Windows vira para o escuro: quem escolheu na mão continua no claro.
    emitSystemChange(true)
    expect(ui.theme).toBe('light')
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })

  it('Shift+clique no botão volta a seguir o sistema', async () => {
    localStorage.setItem('sprintai.theme', 'light')
    stubSystemTheme(true)
    const { wrapper, pinia } = await mountApp()

    await wrapper.find('.sidebar__theme').trigger('click', { shiftKey: true })

    expect(useUiStore(pinia).theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('sprintai.theme')).toBeNull()
  })
})

describe('recarregar o app inteiro', () => {
  async function mountAt(path) {
    const calls = []
    fetch.mockImplementation(async (url) => {
      calls.push(url)
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ status: 'ok', version: '0.1.0', database: { status: 'up' } }),
      }
    })
    const { wrapper, pinia } = await mountApp(path)
    return { wrapper, pinia, calls }
  }

  it('o stream de eventos vale para o app todo, não só para a Home', async () => {
    const { calls } = await mountAt('/semana')

    // Antes ele vivia dentro da HomeView: fora dela, um sync passava despercebido.
    expect(calls.some((url) => url.startsWith('/api/events'))).toBe(true)
  })

  it('sync concluído recarrega a tela aberta mesmo fora da Home', async () => {
    const { calls, pinia } = await mountAt('/semana')
    const weekCalls = () => calls.filter((url) => url.startsWith('/api/week'))
    expect(weekCalls()).toHaveLength(1)

    useRealtimeStore(pinia).record('sync.finished', { id: 371, status: 'success' })
    await flushPromises()

    expect(weekCalls()).toHaveLength(2)
    expect(useRefreshStore(pinia).reason).toBe('sync')
  })
})
