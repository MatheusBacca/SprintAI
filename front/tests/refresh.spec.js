import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import { useIssueDetailStore } from '@/stores/issueDetail'
import { useRefreshStore } from '@/stores/refresh'

const KEY = 'WAI-8360'

const ISSUE = {
  key: KEY,
  url: `https://weon.atlassian.net/browse/${KEY}`,
  summary: 'Ajustes no Histórico de alterações',
  issue_type: 'Problema',
  is_subtask: false,
  status: 'Em Review',
  status_category: 'indeterminate',
  priority: null,
  assignee_name: 'Matheus',
  is_mine: true,
  reporter_name: 'Maycon',
  story_points: 1,
  due_date: null,
  labels: [],
  components: [],
  created_at: '2026-09-10T10:00:00Z',
  updated_at: '2026-09-15T10:00:00Z',
  resolved_at: null,
  synced_at: '2026-09-15T10:00:00Z',
  description_adf: null,
  description_text: 'Descrição',
  parent: null,
  children: [],
  sprints: [],
  dependencies: [],
  blocks: [],
  blocked_by: [],
  comments: [],
  pull_requests: {
    issue_key: KEY,
    status: 'sem_pr',
    status_label: 'Sem PR',
    pr_count: 0,
    open_pr_count: 0,
    build_failed: false,
    last_activity: null,
    repos: [],
  },
}

function json(body) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  }
}

let calls
beforeEach(() => {
  setActivePinia(createPinia())
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      calls.push(url)
      if (url.startsWith('/api/issues/') && url.endsWith('/contexts')) {
        return json({ own: [], linked: [] })
      }
      if (url.startsWith('/api/notes')) return json({ items: [], total: 0 })
      return json(ISSUE)
    }),
  )
})

const issueCalls = () => calls.filter((url) => url === `/api/issues/${KEY}`)

describe('store refresh', () => {
  it('a mesma execução de sync não recarrega duas vezes', () => {
    const refresh = useRefreshStore()

    // O stream avisa primeiro; o polling do status repete o mesmo id logo depois.
    refresh.afterSync(370)
    refresh.afterSync(370)

    expect(refresh.revision).toBe(1)
    expect(refresh.reason).toBe('sync')
  })

  it('execuções diferentes recarregam de novo', () => {
    const refresh = useRefreshStore()

    refresh.afterSync(370)
    refresh.afterSync(371)

    expect(refresh.revision).toBe(2)
  })

  it('sync sem id não é engolido pelo desempate', () => {
    const refresh = useRefreshStore()

    refresh.afterSync(null)
    refresh.afterSync(null)

    expect(refresh.revision).toBe(2)
  })

  it('Recarregar vale mesmo quando nada mudou no espelho', () => {
    const refresh = useRefreshStore()

    refresh.afterSync(370)
    refresh.reload()
    refresh.reload()

    expect(refresh.revision).toBe(3)
    expect(refresh.reason).toBe('manual')
  })
})

describe('cache do painel', () => {
  it('serve do cache até o espelho mudar', async () => {
    const store = useIssueDetailStore()

    await store.load(KEY)
    await store.load(KEY)
    expect(issueCalls()).toHaveLength(1)

    useRefreshStore().reload()
    await store.load(KEY)

    expect(issueCalls()).toHaveLength(2)
  })

  it('recarregar não apaga o que já está na tela', async () => {
    const store = useIssueDetailStore()
    await store.load(KEY)
    useRefreshStore().reload()

    const pending = store.load(KEY)
    // Enquanto busca, o painel continua mostrando a versão anterior — sem "Carregando…".
    expect(store.issues[KEY].loading).toBe(true)
    expect(store.issues[KEY].data.key).toBe(KEY)
    await pending
  })

  it('erro ao recarregar mantém o conteúdo e mostra o motivo', async () => {
    const store = useIssueDetailStore()
    await store.load(KEY)

    useRefreshStore().reload()
    fetch.mockImplementationOnce(async () => {
      throw new TypeError('Failed to fetch')
    })
    await store.load(KEY)

    expect(store.issues[KEY].data.key).toBe(KEY)
    expect(store.issues[KEY].error).toBeTruthy()
  })
})

describe('painel aberto', () => {
  async function mountDrawer() {
    const wrapper = mount(IssueDrawer, { props: { issueKey: KEY } })
    await flushPromises()
    return wrapper
  }

  it('um sync recarrega o painel sem fechar nem trocar de aba', async () => {
    const wrapper = await mountDrawer()
    expect(issueCalls()).toHaveLength(1)

    await wrapper.findAll('.drawer__tab').at(2).trigger('click') // PRs
    useRefreshStore().afterSync(371)
    await flushPromises()

    expect(issueCalls()).toHaveLength(2)
    expect(wrapper.find('.drawer__tab--active').text()).toContain('PRs')
  })

  it('o painel não tem recarregar próprio: o lugar é do ícone de lembretes', async () => {
    const wrapper = await mountDrawer()

    expect(wrapper.find('.drawer__action[title^="Recarregar"]').exists()).toBe(false)
    expect(wrapper.find('.drawer__notes').exists()).toBe(true)
  })
})
