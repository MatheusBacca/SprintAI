import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import AdfRenderer from '@/components/issue/AdfRenderer.js'
import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import AppSidebar from '@/components/shell/AppSidebar.vue'
import { routes } from '@/router/routes'
import { safeUrl } from '@/utils/safeUrl'

const NOW = new Date().toISOString()

function ref(key, extra = {}) {
  return { key, summary: `Resumo ${key}`, status: 'Em Desenvolvimento', status_category: 'indeterminate', issue_type: 'Tarefa', assignee_name: null, in_mirror: true, url: `https://weon.atlassian.net/browse/${key}`, pr: null, ...extra }
}

const ISSUE = {
  key: 'WAI-124',
  url: 'https://weon.atlassian.net/browse/WAI-124',
  summary: 'Implementar camada de integração com OpenAI',
  issue_type: 'Tarefa',
  is_subtask: false,
  status: 'Em Desenvolvimento',
  status_category: 'indeterminate',
  priority: 'High',
  assignee_name: 'Matheus Bacca',
  is_mine: true,
  reporter_name: 'Maycon',
  story_points: 8,
  due_date: '2026-09-19',
  labels: ['backend'],
  components: ['monitoria'],
  created_at: '2026-05-20T10:00:00Z',
  updated_at: '2026-05-22T10:00:00Z',
  resolved_at: null,
  synced_at: NOW,
  description_adf: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Implementar a camada de integração' }] }] },
  description_text: 'Implementar a camada de integração',
  parent: ref('WAI-123', { issue_type: 'Épico' }),
  children: [],
  sprints: [{ id: 3995, name: 'Sprint 42', state: 'active', squad: null }],
  dependencies: [
    { kind: 'blocks', label: 'Bloqueia', items: [
      { ...ref('WAI-126', { pr: { status: 'sem_pr', status_label: 'Sem PR', pr_count: 0, open_pr_count: 0, build_failed: false } }), link_type: 'Blocks', direction: 'outward', label: 'blocks' },
      { ...ref('WAI-125'), link_type: 'Blocks', direction: 'outward', label: 'blocks' },
      { ...ref('OUT-1', { in_mirror: false }), link_type: 'Blocks', direction: 'outward', label: 'blocks' },
    ] },
  ],
  blocks: [],
  blocked_by: [],
  comments: [{ id: '1', author_name: 'Revisor', body_adf: null, body_text: 'Ajustar retry', created_at: '2026-05-21T10:00:00Z', updated_at: null }],
  pull_requests: {
    issue_key: 'WAI-124', status: 'sem_pr', status_label: 'Sem PR', pr_count: 0, open_pr_count: 0, build_failed: false, last_activity: null, repos: [],
  },
}
ISSUE.blocks = ISSUE.dependencies[0].items

const CHANGELOG = {
  issue_key: 'WAI-124',
  truncated: false,
  entries: [
    { id: '10', author_name: 'Matheus Bacca', created_at: '2026-05-22T09:00:00Z', items: [{ field: 'status', from_value: 'Disponivel para análise', to_value: 'Em Desenvolvimento' }] },
  ],
}

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }
}

describe('AdfRenderer', () => {
  it('renderiza marcas, listas e links http e ignora link javascript:', () => {
    const doc = {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [
          { type: 'text', text: 'negrito', marks: [{ type: 'strong' }] },
          { type: 'text', text: ' seguro', marks: [{ type: 'link', attrs: { href: 'https://weon.com.br' } }] },
          { type: 'text', text: ' perigoso', marks: [{ type: 'link', attrs: { href: 'javascript:alert(1)' } }] },
        ] },
        { type: 'bulletList', content: [{ type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'item' }] }] }] },
        { type: 'codeBlock', content: [{ type: 'text', text: 'SELECT 1' }] },
      ],
    }
    const wrapper = mount(AdfRenderer, { props: { doc } })

    expect(wrapper.find('strong').text()).toBe('negrito')
    const links = wrapper.findAll('a')
    expect(links).toHaveLength(1)
    expect(links[0].attributes()).toMatchObject({ href: 'https://weon.com.br/', rel: 'noopener noreferrer', target: '_blank' })
    expect(wrapper.text()).toContain('perigoso')
    expect(wrapper.find('li').text()).toBe('item')
    expect(wrapper.find('pre code').text()).toBe('SELECT 1')
  })

  it('texto com HTML aparece como texto, nunca como markup', () => {
    const doc = { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '<img src=x onerror=alert(1)>' }] }] }
    const wrapper = mount(AdfRenderer, { props: { doc } })

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('<img src=x onerror=alert(1)>')
  })

  it('usa o texto puro quando não há ADF e avisa quando está vazio', () => {
    expect(mount(AdfRenderer, { props: { doc: null, fallback: 'texto legado' } }).text()).toBe('texto legado')
    expect(mount(AdfRenderer, { props: { doc: null } }).text()).toBe('Sem descrição.')
  })

  it('nó desconhecido cai para os filhos; anexo vira marcador', () => {
    const doc = { type: 'doc', content: [
      { type: 'algoNovo', content: [{ type: 'text', text: 'conteúdo' }] },
      { type: 'mediaSingle', content: [{ type: 'media', attrs: { alt: 'print.png' } }] },
    ] }
    const wrapper = mount(AdfRenderer, { props: { doc } })

    expect(wrapper.text()).toContain('conteúdo')
    expect(wrapper.text()).toContain('print.png (abrir no Jira)')
  })

  it.each([
    ['https://x.com/a', 'https://x.com/a'],
    ['mailto:a@b.com', 'mailto:a@b.com'],
    ['javascript:alert(1)', null],
    ['data:text/html,oi', null],
    ['não é url', null],
  ])('safeUrl(%s)', (input, expected) => {
    expect(safeUrl(input)).toBe(expected)
  })
})

describe('IssueDrawer', () => {
  let calls
  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    vi.stubGlobal('fetch', vi.fn(async (url) => {
      calls.push(url)
      if (url === '/api/issues/WAI-124') return json(200, ISSUE)
      if (url === '/api/issues/WAI-124/changelog') return json(200, CHANGELOG)
      if (url === '/api/issues/WAI-999') return json(404, { detail: 'WAI-999 não está no espelho local.' })
      throw new Error(`não mockado: ${url}`)
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  const mountDrawer = async (key = 'WAI-124') => {
    const wrapper = mount(IssueDrawer, { props: { issueKey: key }, attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  it('cabeçalho e aba Detalhes como no print', async () => {
    const wrapper = await mountDrawer()

    expect(wrapper.find('.drawer__title').text()).toBe('Implementar camada de integração com OpenAI')
    expect(wrapper.find('.drawer__key').text()).toBe('WAI-124')
    expect(wrapper.find('.drawer__key').attributes('href')).toBe('https://weon.atlassian.net/browse/WAI-124')
    expect(wrapper.findAll('.drawer__bar > *').map((el) => el.classes()[0])).toEqual(['drawer__icon', 'drawer__type', 'drawer__key', 'drawer__chip', 'pr-badge', 'drawer__action', 'drawer__action'])
    expect(wrapper.findAll('.drawer__tab').map((t) => t.text())).toEqual(['Detalhes', 'Dependências4', 'PRs', 'Histórico1', 'Contextos'])
    expect(wrapper.find('.drawer__status').text()).toBe(ISSUE.status)
    expect(wrapper.find('.drawer__bar').text()).not.toContain(ISSUE.status)
    expect(wrapper.text()).toContain('Implementar a camada de integração')
    const fields = Object.fromEntries(wrapper.findAll('.details__field').map((f) => [f.find('dt').text(), f.find('dd').text()]))
    expect(fields).toMatchObject({ 'Story Points': '8', Sprint: 'Sprint 42', Componente: 'monitoria', Responsável: 'Matheus Bacca' })
    expect(wrapper.text()).toContain('Bloqueia (3)')
    expect(wrapper.text()).toContain('Esta tarefa bloqueia 3 outras tarefas')
    wrapper.unmount()
  })

  it('avisa que está pronto só quando tarefa e contagens chegaram', async () => {
    const wrapper = mount(IssueDrawer, { props: { issueKey: 'WAI-124' }, attachTo: document.body })
    expect(wrapper.emitted('ready')).toBeUndefined()

    await flushPromises()

    expect(wrapper.emitted('ready')).toHaveLength(1)
    wrapper.unmount()
  })

  it('o ícone de lembretes do cabeçalho alterna entre lembretes e detalhes', async () => {
    const wrapper = await mountDrawer()
    const button = wrapper.find('.drawer__notes')
    expect(button.attributes('aria-pressed')).toBe('false')

    await button.trigger('click')
    expect(button.attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('.drawer__tab--active').exists()).toBe(false)
    expect(wrapper.find('.issue-notes').exists()).toBe(true)

    await button.trigger('click')
    expect(wrapper.find('.drawer__tab--active').text()).toBe('Detalhes')
    expect(wrapper.find('.issue-notes').exists()).toBe(false)
    wrapper.unmount()
  })

  describe('copiar a descrição', () => {
    async function blob(item, type) {
      const value = item[type]
      if (typeof value === 'string') return value
      // Blob do jsdom não tem .text(): lê pelo FileReader.
      return new Promise((resolve) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result)
        reader.readAsText(value)
      })
    }

    it('copia a descrição formatada e em texto puro, e avisa no botão', async () => {
      const written = []
      vi.stubGlobal('ClipboardItem', class ClipboardItemStub {
        constructor(items) {
          this.items = items
        }
      })
      vi.stubGlobal('navigator', { clipboard: { write: vi.fn(async (items) => written.push(items[0].items)) } })
      const wrapper = await mountDrawer()

      await wrapper.find('.details__copy').trigger('click')
      await flushPromises()

      expect(written).toHaveLength(1)
      expect(await blob(written[0], 'text/plain')).toBe('Implementar a camada de integração')
      expect(await blob(written[0], 'text/html')).toContain('Implementar a camada de integração')
      expect(wrapper.find('.details__copy--ok').text()).toBe('Copiada')
      wrapper.unmount()
    })

    it('sem os dois formatos, copia só o texto', async () => {
      const written = []
      vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn(async (text) => written.push(text)) } })
      const wrapper = await mountDrawer()

      await wrapper.find('.details__copy').trigger('click')
      await flushPromises()

      expect(written).toEqual(['Implementar a camada de integração'])
      wrapper.unmount()
    })

    it('tarefa sem descrição não mostra o botão', async () => {
      const issue = { ...ISSUE, description_adf: null, description_text: '  ' }
      vi.stubGlobal('fetch', vi.fn(async (url) => {
        if (url === '/api/issues/WAI-124') return json(200, issue)
        throw new Error(`não mockado: ${url}`)
      }))
      const wrapper = await mountDrawer()

      expect(wrapper.find('.details__copy').exists()).toBe(false)
      wrapper.unmount()
    })
  })

  describe('bloqueio e cor, com a regra do card do canvas', () => {
    const blocker = (key) => ({ ...ref(key), link_type: 'Blocks', direction: 'inward', label: 'is blocked by' })

    async function mountWith(overrides) {
      const issue = { ...ISSUE, ...overrides }
      vi.stubGlobal('fetch', vi.fn(async (url) => {
        if (url === '/api/issues/WAI-124') return json(200, issue)
        throw new Error(`não mockado: ${url}`)
      }))
      return mountDrawer()
    }

    it('bloqueador sem PR: ícone de bloqueio e "É bloqueada por" só com os pendentes', async () => {
      const wrapper = await mountWith({ blocked_by: [blocker('WAI-2'), blocker('WAI-3')], blockers_without_pr: ['WAI-3'] })

      expect(wrapper.find('.drawer__icon').attributes('data-blocked')).toBeDefined()
      expect(wrapper.text()).toContain('É bloqueada por (1)')
      expect(wrapper.findAll('.details__heading--alert + .details__list li').length).toBe(1)
      wrapper.unmount()
    })

    it('todos os bloqueadores com PR aberta: volta o ícone do tipo e some a seção', async () => {
      const wrapper = await mountWith({ blocked_by: [blocker('WAI-2')], blockers_without_pr: [] })

      expect(wrapper.find('.drawer__icon').attributes('data-blocked')).toBeUndefined()
      expect(wrapper.text()).not.toContain('É bloqueada por')
      wrapper.unmount()
    })

    it('o painel ganha o contorno na cor da etapa do status', async () => {
      const wrapper = await mountWith({ stage: { id: 'desenvolvimento', label: 'Desenvolvimento', color: '#2f7cf6' } })

      expect(wrapper.find('.drawer').classes()).toContain('drawer--toned')
      expect(wrapper.find('.drawer').attributes('style')).toContain('--tone: #2f7cf6')
      wrapper.unmount()
    })

    it('status sem etapa mapeada mantém a borda padrão', async () => {
      const wrapper = await mountWith({ stage: null })

      expect(wrapper.find('.drawer').classes()).not.toContain('drawer--toned')
      wrapper.unmount()
    })
  })

  it('clicar numa tarefa citada pede para abri-la; fora do espelho vira link do Jira', async () => {
    const wrapper = await mountDrawer()

    await wrapper.findAll('.drawer__tab')[1].trigger('click')
    const keys = wrapper.findAll('.ref__key')
    await keys.find((k) => k.text() === 'WAI-126').trigger('click')
    expect(wrapper.emitted('open')[0]).toEqual(['WAI-126'])

    const external = keys.find((k) => k.text().startsWith('OUT-1'))
    expect(external.element.tagName).toBe('A')
    wrapper.unmount()
  })

  it('Histórico junta comentários e mudanças do Jira, mais recente primeiro', async () => {
    const wrapper = await mountDrawer()

    await wrapper.findAll('.drawer__tab')[3].trigger('click')
    await flushPromises()

    expect(calls).toContain('/api/issues/WAI-124/changelog')
    const events = wrapper.findAll('.event')
    expect(events.map((e) => e.attributes('data-kind'))).toEqual(['change', 'comment'])
    expect(events[0].text()).toContain('Status')
    expect(events[0].text()).toContain('Em Desenvolvimento')
    expect(events[1].text()).toContain('Ajustar retry')
    wrapper.unmount()
  })

  it('Esc fecha o painel', async () => {
    const wrapper = await mountDrawer()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('tarefa fora do espelho mostra o erro', async () => {
    const wrapper = await mountDrawer('WAI-999')

    expect(wrapper.find('.drawer__error').text()).toBe('WAI-999 não está no espelho local.')
    wrapper.unmount()
  })

  it('aba PRs mostra repositório, aprovações, pedido de ajuste, revisores e branch', async () => {
    const withPrs = {
      ...ISSUE,
      pull_requests: {
        issue_key: 'WAI-124', status: 'ajustes_requisitados', status_label: 'Ajustes requisitados', pr_count: 1, open_pr_count: 1, build_failed: true, last_activity: NOW,
        repos: [{
          repo_slug: 'monitoria', status: 'ajustes_requisitados', status_label: 'Ajustes requisitados',
          pull_requests: [{
            repo_slug: 'monitoria', id: 412, title: 'WAI-124 integração', state: 'OPEN', status: 'ajustes_requisitados', status_label: 'Ajustes requisitados',
            draft: false, source_branch: 'feature/WAI-124', destination_branch: 'main', url: 'https://bitbucket.org/weonrepo/monitoria/pull-requests/412',
            updated_on: NOW, approvals: 1, changes_requested: 1, build_status: 'FAILED', build_failed: true, comment_count: 3, match: 'title', fix_pushed: false,
            reviewers: [{ name: 'Ana', role: 'REVIEWER', approved: true, state: 'approved' }, { name: 'Bruno', role: 'REVIEWER', approved: false, state: 'changes_requested' }],
          }],
          branches: [{ name: 'WAI-124-antiga', target_date: NOW, stale: true }],
        }],
      },
    }
    fetch.mockImplementation(async (url) => (url === '/api/issues/WAI-124' ? json(200, withPrs) : json(200, CHANGELOG)))
    const wrapper = await mountDrawer()

    await wrapper.findAll('.drawer__tab')[2].trigger('click')

    const text = wrapper.find('.prs').text()
    expect(text).toContain('monitoria')
    expect(text).toContain('#412 WAI-124 integração')
    expect(text).toContain('1 aprovação(ões)')
    expect(text).toContain('1 pedido(s) de ajuste')
    expect(text).toContain('Build falhou')
    expect(text).toContain('citada no título')
    expect(text).toContain('sobra de merge')
    expect(wrapper.findAll('.pr__reviewers li').map((r) => r.attributes('data-state'))).toEqual(['approved', 'changes_requested'])
    wrapper.unmount()
  })
})

describe('AppSidebar recolhível', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('recolhe para só ícones, mostra o nome no hover e lembra a preferência', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const wrapper = mount(AppSidebar, { global: { plugins: [router] } })

    expect(wrapper.classes()).not.toContain('sidebar--collapsed')
    await wrapper.find('.sidebar__toggle').trigger('click')

    expect(wrapper.classes()).toContain('sidebar--collapsed')
    expect(wrapper.find('.sidebar__item').attributes('title')).toBe('Home')
    expect(localStorage.getItem('sprintai.sidebarCollapsed')).toBe('1')

    setActivePinia(createPinia())
    const again = mount(AppSidebar, { global: { plugins: [router] } })
    expect(again.classes()).toContain('sidebar--collapsed')
  })
})
