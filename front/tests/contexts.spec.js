import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ContextCard from '@/components/contexts/ContextCard.vue'
import ContextEditor from '@/components/contexts/ContextEditor.vue'
import ContextResolveDialog from '@/components/contexts/ContextResolveDialog.vue'
import IssueContextsTab from '@/components/issue/IssueContextsTab.vue'
import ContextsView from '@/views/ContextsView.vue'
import { routes } from '@/router/routes'
import { useContextsStore } from '@/stores/contexts'

const NOW = new Date().toISOString()
const issue = (key, extra = {}) => ({ key, summary: `Resumo ${key}`, status: 'Em Desenvolvimento', status_category: 'indeterminate', in_mirror: true, url: `https://weon.atlassian.net/browse/${key}`, ...extra })

function ctx(id, extra = {}) {
  return {
    id,
    issue: issue('WAI-1'),
    kind: 'finding',
    title: `Contexto ${id}`,
    body: 'Retry sem jitter derruba o provedor',
    tags: [],
    status: 'open',
    resolved_in: null,
    resolution: '',
    resolved_at: null,
    source: 'manual',
    created_at: NOW,
    updated_at: NOW,
    relations: [],
    rank: null,
    ...extra,
  }
}

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

let calls
function routeFetch(handler) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const body = init.body ? JSON.parse(init.body) : undefined
      calls.push({ method: init.method ?? 'GET', url, body })
      return handler({ method: init.method ?? 'GET', url, body })
    }),
  )
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('ContextCard', () => {
  it('ponto em aberto mostra status, tarefa de origem e emite resolver', async () => {
    const wrapper = mount(ContextCard, {
      props: { context: ctx(1, { kind: 'open_point', title: 'Definir limite', relations: [{ ...issue('WAI-2'), relation: 'continues' }] }), resolveLabel: 'Resolver aqui' },
    })

    expect(wrapper.find('.ctx__kind').text()).toContain('Ponto em aberto')
    expect(wrapper.find('.ctx__status--open').exists()).toBe(true)
    expect(wrapper.find('.ctx__issue').text()).toBe('WAI-1')
    expect(wrapper.find('.ctx__rel').text()).toBe('continua WAI-2')

    await wrapper.find('.ctx__resolve').trigger('click')
    expect(wrapper.find('.ctx__resolve').text()).toContain('Resolver aqui')
    expect(wrapper.emitted('resolve')[0][0].id).toBe(1)

    await wrapper.find('.ctx__rel .ctx__link').trigger('click')
    expect(wrapper.emitted('open-issue')[0][0].key).toBe('WAI-2')
  })

  it('resolvido mostra onde e como, sem a relação de resolução duplicada, e reabre', async () => {
    const wrapper = mount(ContextCard, {
      props: {
        context: ctx(2, {
          kind: 'open_point',
          status: 'resolved',
          resolved_in: issue('WAI-3'),
          resolution: 'Limite de 5 com backoff',
          relations: [{ ...issue('WAI-3'), relation: 'resolves' }],
        }),
        hideIssue: true,
      },
    })

    expect(wrapper.find('.ctx__status--resolved').text()).toContain('Resolvido em WAI-3')
    expect(wrapper.find('.ctx__resolution').text()).toBe('Limite de 5 com backoff')
    expect(wrapper.findAll('.ctx__rel')).toHaveLength(0)
    expect(wrapper.find('.ctx__issue').exists()).toBe(false)
    expect(wrapper.find('.ctx__resolve').exists()).toBe(false)

    await wrapper.find('button[title="Reabrir"]').trigger('click')
    expect(wrapper.emitted('reopen')).toHaveLength(1)
  })

  it('destaca sem acento, recolhe texto longo e confirma exclusão', async () => {
    const wrapper = mount(ContextCard, { props: { context: ctx(3, { title: 'Integração <b>x</b>', body: 'a'.repeat(600) }), highlight: 'integracao' } })

    expect(wrapper.find('mark.hit').text()).toBe('Integração')
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.find('.ctx__body').text().length).toBeLessThan(500)
    await wrapper.find('.ctx__more').trigger('click')
    expect(wrapper.find('.ctx__body').text()).toHaveLength(600)

    const del = wrapper.find('.ctx__delete')
    await del.trigger('click')
    expect(wrapper.emitted('delete')).toBeUndefined()
    await del.trigger('click')
    expect(wrapper.emitted('delete')).toHaveLength(1)
  })
})

describe('ContextEditor e resolução', () => {
  const setValue = async (el, value) => {
    el.value = value
    el.dispatchEvent(new Event('input'))
    await flushPromises()
  }

  it('cria com tipo, relações e "continua"; sem chave válida não salva', async () => {
    routeFetch(({ method }) => (method === 'POST' ? json(201, ctx(9)) : json(200, {})))
    const store = useContextsStore()
    mount(ContextEditor, { attachTo: document.body })
    store.openEditor(null, { kind: 'decision' })
    await flushPromises()

    const dialog = document.body.querySelector('.ctx-editor')
    const submit = dialog.querySelector('button[type="submit"]')
    expect(dialog.querySelector('[aria-checked="true"]').textContent).toContain('Decisão')
    expect(document.activeElement).toBe(dialog.querySelector('#ctx-issue'))

    await setValue(dialog.querySelector('#ctx-title'), 'Usar backoff exponencial')
    await setValue(dialog.querySelector('#ctx-issue'), 'wai')
    expect(submit.disabled).toBe(true)

    await setValue(dialog.querySelector('#ctx-issue'), 'wai-8295')
    await setValue(dialog.querySelector('#ctx-related'), 'WAI-1 wai-2')
    dialog.querySelector('#ctx-related').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await setValue(dialog.querySelector('#ctx-continues'), 'wai-2')
    await flushPromises()
    expect(submit.disabled).toBe(false)

    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
    await flushPromises()

    const post = calls.find((c) => c.method === 'POST')
    expect(post.url).toBe('/api/contexts')
    expect(post.body).toEqual({
      issue_key: 'wai-8295',
      kind: 'decision',
      title: 'Usar backoff exponencial',
      body: '',
      tags: [],
      relations: [
        { issue_key: 'WAI-1', relation: 'relates' },
        { issue_key: 'WAI-2', relation: 'continues' },
      ],
    })
    expect(store.editor.open).toBe(false)
    expect(store.revision).toBe(1)
  })

  it('ponto resolvido não troca de tipo no editor', async () => {
    const store = useContextsStore()
    mount(ContextEditor, { attachTo: document.body })
    store.openEditor(ctx(4, { kind: 'open_point', status: 'resolved', resolved_in: issue('WAI-2') }))
    await flushPromises()

    const kinds = [...document.body.querySelectorAll('.ctx-editor__kind')]
    expect(kinds.filter((k) => k.disabled).map((k) => k.textContent.trim())).toEqual(['Achado', 'Correção', 'Decisão', 'Resumo'])
  })

  it('resolve informando a tarefa e como', async () => {
    routeFetch(() => json(200, ctx(5, { kind: 'open_point', status: 'resolved' })))
    const store = useContextsStore()
    mount(ContextResolveDialog, { attachTo: document.body })
    store.openResolver(ctx(5, { kind: 'open_point', title: 'Definir limite' }), 'WAI-2')
    await flushPromises()

    const dialog = document.body.querySelector('.resolve')
    expect(dialog.textContent).toContain('aberto em WAI-1')
    expect(document.activeElement).toBe(dialog.querySelector('#resolve-text'))
    await setValue(dialog.querySelector('#resolve-text'), 'Limite de 5')
    dialog.querySelector('button[type="submit"]').click()
    await flushPromises()

    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/contexts/5/resolve', body: { issue_key: 'WAI-2', resolution: 'Limite de 5' } })
    expect(store.resolver.open).toBe(false)
  })
})

describe('IssueContextsTab', () => {
  it('mostra desta tarefa, citações e pontos próximos com "Resolver aqui"', async () => {
    routeFetch(() =>
      json(200, {
        own: [ctx(1, { issue: issue('WAI-7') })],
        linked: [ctx(2, { issue: issue('WAI-3'), relations: [{ ...issue('WAI-7'), relation: 'relates' }] })],
        nearby_open: [ctx(3, { kind: 'open_point', issue: issue('WAI-8') })],
      }),
    )
    const store = useContextsStore()
    const wrapper = mount(IssueContextsTab, { props: { issueKey: 'WAI-7' } })
    await flushPromises()

    expect(calls[0].url).toBe('/api/issues/WAI-7/contexts')
    expect(wrapper.emitted('count')[0]).toEqual([2])
    const sections = wrapper.findAll('.issue-ctx__section')
    expect(sections.map((s) => s.find('h3').text())).toEqual([
      'Desta tarefa 1',
      'De outras tarefas que citam esta 1',
      'Em aberto em tarefas próximas 1',
    ])
    expect(sections[0].find('.ctx__issue').exists()).toBe(false)

    await sections[2].find('.ctx__resolve').trigger('click')
    expect(store.resolver).toMatchObject({ open: true, issue_key: 'WAI-7' })
    expect(store.resolver.context.id).toBe(3)

    await wrapper.findAll('.issue-ctx__kind')[0].trigger('click')
    expect(store.editor.draft).toMatchObject({ kind: 'open_point', issue_key: 'WAI-7' })

    await sections[1].find('.ctx__issue').trigger('click')
    expect(wrapper.emitted('open')[0]).toEqual(['WAI-3'])
  })
})

describe('ContextsView', () => {
  it('abre em "Pontos em aberto", agrupa por tarefa e troca de filtro pela URL', async () => {
    routeFetch(({ url }) => {
      if (url === '/api/contexts/counts') return json(200, { open_points: 2, by_kind: { open_point: 3, finding: 1 } })
      if (url.startsWith('/api/issues/')) return json(404, { detail: 'fora do teste' })
      return json(200, {
        items: [ctx(1, { kind: 'open_point' }), ctx(2, { kind: 'open_point', issue: issue('WAI-2') }), ctx(3, { kind: 'open_point' })],
        total: 3,
      })
    })
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/contextos')
    await router.isReady()
    const wrapper = mount(ContextsView, { global: { plugins: [router] } })
    await flushPromises()

    expect(decodeURIComponent(calls.find((c) => c.url.startsWith('/api/contexts?')).url)).toBe('/api/contexts?kind=open_point&status=open&limit=200')
    expect(wrapper.findAll('.contexts__group').map((g) => g.attributes('data-issue'))).toEqual(['WAI-1', 'WAI-2'])
    expect(wrapper.findAll('.contexts__group')[0].findAll('.ctx')).toHaveLength(2)
    expect(wrapper.find('.contexts__filter--on').text()).toBe('Pontos em aberto2')

    const decisions = wrapper.findAll('.contexts__filter').find((b) => b.text().startsWith('Decisões'))
    await decisions.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.filtro).toBe('decision')
    expect(calls.at(-1).url).toBe('/api/contexts?kind=decision&limit=200')

    await wrapper.find('.contexts__top .btn--primary').trigger('click')
    expect(useContextsStore().editor.draft.kind).toBe('decision')

    await wrapper.find('.contexts__group-key').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tarefa).toBe('WAI-1')
  })
})
