import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import GlobalSearch from '@/components/search/GlobalSearch.vue'
import GlobalShortcuts from '@/components/shell/GlobalShortcuts.vue'
import { routes } from '@/router/routes'
import { useNotesStore } from '@/stores/notes'
import { useSearchStore } from '@/stores/search'
import { useUiStore } from '@/stores/ui'
import { highlightTerms, searchTerms } from '@/utils/highlight'
import { DEFAULT_BINDINGS } from '@/utils/shortcuts'

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => structuredClone(body), text: async () => '' }
}

let calls
function routeFetch(handler) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      calls.push({ method: init.method ?? 'GET', url })
      return handler({ method: init.method ?? 'GET', url })
    }),
  )
}

const hit = (type, id, extra = {}) => ({
  type,
  id,
  title: `Título ${id}`,
  snippet: 'retry com backoff exponencial',
  issue_key: 'WAI-1',
  issue_keys: ['WAI-1'],
  issue_summary: 'Retry no client',
  issue_in_mirror: true,
  issue_url: 'https://weon.atlassian.net/browse/WAI-1',
  meta: {},
  occurred_at: new Date().toISOString(),
  rank: 1,
  ...extra,
})

const RESULT = {
  query: 'retry',
  total: 9,
  groups: [
    { type: 'issue', total: 6, items: [hit('issue', 'WAI-1', { title: 'Retry exponencial', meta: { status: 'Em Desenvolvimento', issue_type: 'Tarefa' } })] },
    { type: 'comment', total: 1, items: [hit('comment', 'c1', { title: 'Comentário de Ana', issue_key: 'WAI-2' })] },
    {
      type: 'pull_request',
      total: 1,
      items: [
        hit('pull_request', 'monitoria#10', {
          issue_key: null,
          issue_keys: [],
          issue_in_mirror: false,
          meta: { url: 'https://bitbucket.org/weonrepo/monitoria/pull-requests/10', state: 'OPEN', repo_slug: 'monitoria', pr_id: 10 },
        }),
      ],
    },
    { type: 'note', total: 1, items: [hit('note', '7', { title: 'Lembrar do retry', meta: { color: 'blue' } })] },
  ],
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  vi.unstubAllGlobals()
  document.getSelection()?.removeAllRanges()
  document.body.innerHTML = ''
})

describe('destaque de vários termos', () => {
  it('marca cada termo sem acento e junta sobreposições', () => {
    expect(highlightTerms('Integração e retry exponencial', ['integracao', 'exponen', 'ponencial'])).toEqual([
      { text: 'Integração', hit: true },
      { text: ' e retry ', hit: false },
      { text: 'exponencial', hit: true },
    ])
    expect(searchTerms('retry or "exponencial" -client a')).toEqual(['retry', 'exponencial', 'client'])
  })
})

describe('store da busca', () => {
  it('não busca com menos de 2 letras; "Tudo" traz 5 por tipo; filtro traz 20 e pagina', async () => {
    routeFetch(({ url }) =>
      url.includes('offset=') ? json(200, { ...RESULT, groups: [{ type: 'issue', total: 6, items: [hit('issue', 'WAI-9')] }] }) : json(200, RESULT),
    )
    const store = useSearchStore()

    store.query = 'r'
    await store.run()
    expect(calls).toHaveLength(0)

    store.query = 'retry'
    await store.run()
    expect(calls[0].url).toBe('/api/search?q=retry&period=any&limit=5')
    expect(store.totals).toEqual({ issue: 6, comment: 1, pull_request: 1, note: 1 })

    await store.setType('issue')
    expect(calls[1].url).toBe('/api/search?q=retry&type=issue&period=any&limit=20')
    await store.loadMore()
    expect(calls[2].url).toBe('/api/search?q=retry&type=issue&period=any&limit=20&offset=1')
    expect(store.result.groups[0].items.at(-1).id).toBe('WAI-9')
    expect(store.totals.comment).toBe(1) // mantém as contagens dos outros tipos
  })
})

describe('GlobalSearch', () => {
  async function mountSearch(path = '/') {
    routeFetch(({ url }) => {
      if (url === '/api/notes/7') {
        return json(200, { id: 7, title: 'Lembrar do retry', body: '', color: 'blue', tags: [], pinned: false, remind_at: null, issues: [] })
      }
      return json(200, RESULT)
    })
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push(path)
    await router.isReady()
    const wrapper = mount(GlobalSearch, { props: { debounceMs: 0 }, attachTo: document.body, global: { plugins: [router] } })
    const store = useSearchStore()
    store.openSearch('retry')
    await flushPromises()
    return { wrapper, router, store }
  }

  const modal = () => document.body.querySelector('.gsearch')
  const press = (key) => document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))

  it('agrupa, destaca, mostra contagens e "ver todos"', async () => {
    const { wrapper, store } = await mountSearch()

    expect([...modal().querySelectorAll('.gsearch__group')].map((g) => g.dataset.type)).toEqual(['issue', 'comment', 'pull_request', 'note'])
    expect(modal().querySelector('.gsearch__type--on').textContent).toBe('Tudo9')
    expect(modal().querySelector('.gsearch__hit mark.hit').textContent).toBe('Retry')
    expect(modal().querySelector('[data-type="pull_request"] .gsearch__meta').textContent).toContain('monitoria #10')

    modal().querySelector('.gsearch__all').click()
    await flushPromises()
    expect(store.type).toBe('issue')
    wrapper.unmount()
  })

  it('comentário abre o painel da tarefa na aba Histórico, a partir de qualquer tela', async () => {
    const { wrapper, router, store } = await mountSearch('/configuracoes')

    press('ArrowDown')
    await flushPromises()
    expect(modal().querySelectorAll('.gsearch__hit')[1].getAttribute('aria-selected')).toBe('true')
    press('Enter')
    await flushPromises()

    expect(store.open).toBe(false)
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/sprints?tarefa=WAI-2'))
    expect(useUiStore().consumeIssueTab('WAI-2')).toBe('historico')
    wrapper.unmount()
  })

  it('numa tela com painel, abre ali mesmo', async () => {
    const { wrapper, router } = await mountSearch('/lembretes?filtro=vencidos')

    press('Enter')
    await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/lembretes?filtro=vencidos&tarefa=WAI-1'))
    wrapper.unmount()
  })

  it('PR fora do espelho abre o Bitbucket; lembrete abre o editor', async () => {
    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)
    const { wrapper, store } = await mountSearch('/lembretes')

    modal().querySelector('[data-type="pull_request"] .gsearch__hit').click()
    await flushPromises()
    expect(openSpy).toHaveBeenCalledWith('https://bitbucket.org/weonrepo/monitoria/pull-requests/10', '_blank', 'noopener')

    store.openSearch()
    await flushPromises()
    modal().querySelector('[data-type="note"] .gsearch__hit').click()
    await flushPromises()
    expect(calls.at(-1).url).toBe('/api/notes/7')
    expect(useNotesStore().editor).toMatchObject({ open: true, draft: { id: 7, title: 'Lembrar do retry' } })
    wrapper.unmount()
  })
})

describe('atalho da busca', () => {
  it('Ctrl+K abre a busca com o texto selecionado e fecha no segundo toque', async () => {
    routeFetch(() => json(200, { bindings: DEFAULT_BINDINGS, defaults: DEFAULT_BINDINGS }))
    const wrapper = mount(GlobalShortcuts, { attachTo: document.body })
    await flushPromises()
    const store = useSearchStore()

    const p = document.createElement('p')
    p.textContent = 'backoff exponencial'
    document.body.append(p)
    const range = document.createRange()
    range.selectNodeContents(p)
    document.getSelection().addRange(range)

    const event = new KeyboardEvent('keydown', { code: 'KeyK', key: 'k', ctrlKey: true, bubbles: true, cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect([store.open, store.query]).toEqual([true, 'backoff exponencial'])

    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyK', key: 'k', ctrlKey: true, bubbles: true }))
    expect(store.open).toBe(false)
    wrapper.unmount()
  })
})
