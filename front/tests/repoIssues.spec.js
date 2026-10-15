import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import RepoIssuesMenu from '@/components/shell/RepoIssuesMenu.vue'
import TopbarTip from '@/components/shell/TopbarTip.vue'
import { useRefreshStore } from '@/stores/refresh'
import { useRepoIssuesStore } from '@/stores/repoIssues'

const DEV = { id: 'desenvolvimento', label: 'Desenvolvimento', color: '#2f7cf6' }
const DONE = { id: 'concluido', label: 'Concluído', color: '#10b981' }

const issue = (key, status, stage) => ({ key, summary: `[monitoria] Tarefa ${key}`, issue_type: 'Tarefa', status, stage })

const REPOS = {
  repos: [
    {
      slug: 'monitoria',
      bb_slug: 'monitoria',
      local: true,
      color: '#ea580c',
      project_key: 'ORGANIA',
      project_name: 'OrganIA',
      issue_count: 3,
      sprints: [
        { id: 4100, name: 'Sprint 78 - Growth', state: 'future', position: 'proxima', issues: [issue('WAI-9482', 'Em Desenvolvimento', DEV)] },
        { id: 4066, name: 'Sprint 77 - Growth', state: 'active', position: 'atual', issues: [issue('WAI-9222', 'Concluído', DONE)] },
        { id: 4031, name: 'Sprint 76 - Growth', state: 'closed', position: 'anterior', issues: [issue('WAI-7737', 'Cruzeiro', null)] },
      ],
    },
    {
      slug: 'qualificai',
      bb_slug: 'qualificai',
      local: true,
      color: null,
      project_key: 'ORGANIA',
      project_name: 'OrganIA',
      issue_count: 1,
      sprints: [{ id: 4031, name: 'Sprint 76 - Growth', state: 'closed', position: 'anterior', issues: [issue('WAI-8858', 'Concluído', DONE)] }],
    },
    {
      slug: 'supervisor-web',
      bb_slug: 'supervisor-web',
      local: true,
      color: null,
      project_key: 'WEON',
      project_name: 'WeON',
      issue_count: 2,
      sprints: [{ id: 4066, name: 'Sprint 77 - Growth', state: 'active', position: 'atual', issues: [issue('WAI-9224', 'DISPONIVEL PARA TESTES', DONE), issue('WAI-9152', 'Concluído', DONE)] }],
    },
    {
      // A WAI-9224 é `[supervisor / weaction-api]`: está nos dois repos do mesmo projeto.
      slug: 'weaction-api',
      bb_slug: 'weaction-api',
      local: true,
      color: null,
      project_key: 'WEON',
      project_name: 'WeON',
      issue_count: 1,
      sprints: [{ id: 4066, name: 'Sprint 77 - Growth', state: 'active', position: 'atual', issues: [issue('WAI-9224', 'DISPONIVEL PARA TESTES', DONE)] }],
    },
    {
      slug: 'communicator',
      bb_slug: 'communicator',
      local: true,
      color: null,
      project_key: null,
      project_name: null,
      issue_count: 1,
      sprints: [{ id: 4100, name: 'Sprint 78 - Growth', state: 'future', position: 'proxima', issues: [issue('WAI-9486', 'Disponivel para análise', null)] }],
    },
  ],
}

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

let calls
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      calls.push(url)
      return url.includes('/workspace/repo-issues') ? json(200, REPOS) : json(200, {})
    }),
  )
})
/**
 * Rotas leves no lugar das reais: o teste só confere para onde o clique leva. Com as reais,
 * chegar em `/sprints` carregava a SprintView inteira (Vue Flow) por import dinâmico, e com
 * a máquina carregada a navegação passava do tempo do `waitFor`.
 */
const EMPTY = { template: '<div />' }
const ROUTES = [
  { path: '/', name: 'home', component: EMPTY },
  { path: '/sprints', name: 'sprints', component: EMPTY },
]

// Teste que falha no meio não chega no `unmount()` dele: o painel ficaria ouvindo o
// documento por cima do teste seguinte.
const mounted = []

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

async function mountMenu() {
  const router = createRouter({ history: createMemoryHistory(), routes: ROUTES })
  router.push('/')
  await router.isReady()
  const wrapper = mount(RepoIssuesMenu, { attachTo: document.body, global: { plugins: [router] } })
  mounted.push(wrapper)
  await wrapper.find('.repos__toggle').trigger('click')
  await flushPromises()
  return { wrapper, router }
}

const loads = () => calls.filter((url) => url.includes('/workspace/repo-issues')).length

describe('RepoIssuesMenu', () => {
  it('lista as WAIs do repo na próxima, na atual e na anterior, na cor da etapa', async () => {
    const { wrapper } = await mountMenu()

    expect(wrapper.findAll('.repos__repo').map((b) => b.attributes('data-slug'))).toEqual(['monitoria', 'qualificai', 'supervisor-web', 'weaction-api', 'communicator'])
    expect(wrapper.find('.repos__repo--on').attributes('data-slug')).toBe('monitoria')
    expect(wrapper.findAll('.repos__sprint-name').map((h) => [h.find('.repos__sprint-text').text(), h.find('.repos__badge').text()])).toEqual([
      ['Sprint 78 - Growth', 'próxima'],
      ['Sprint 77 - Growth', 'atual'],
      ['Sprint 76 - Growth', 'anterior'],
    ])

    const row = (key) => wrapper.find(`.repos__issue[data-key="${key}"]`)
    expect(row('WAI-9482').attributes('style')).toContain('--tone: #2f7cf6')
    expect(row('WAI-9482').find('.repos__status').text()).toBe('Em Desenvolvimento')
    expect(row('WAI-9222').attributes('style')).toContain('--tone: #10b981')
    // Status sem etapa mapeada fica no cinza da borda, como o card no canvas.
    expect(row('WAI-7737').attributes('style')).toContain('--tone: var(--color-border-strong)')
  })

  it('trocar de repo mostra as WAIs dele e a escolha fica lembrada', async () => {
    const { wrapper } = await mountMenu()

    await wrapper.find('.repos__repo[data-slug="qualificai"]').trigger('click')

    expect(wrapper.findAll('.repos__issue').map((b) => b.attributes('data-key'))).toEqual(['WAI-8858'])
    expect(localStorage.getItem('sprintai.repoIssues.repo')).toBe('qualificai')

    setActivePinia(createPinia())
    expect(useRepoIssuesStore().selected).toBe('qualificai')
  })

  it('clicar na WAI leva ao canvas da sprint dela, com o card aberto, e fecha o painel', async () => {
    const { wrapper, router } = await mountMenu()

    await wrapper.find('.repos__issue[data-key="WAI-9482"]').trigger('click')

    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/sprints?tarefa=WAI-9482&sprint=4100'))
    expect(wrapper.find('.repos__panel').exists()).toBe(false)
  })

  it('aberto, relê quando o espelho muda; fechado, só na próxima abertura', async () => {
    const { wrapper } = await mountMenu()
    const refresh = useRefreshStore()
    expect(loads()).toBe(1)

    refresh.bump('sync')
    await flushPromises()
    expect(loads()).toBe(2)

    await wrapper.find('.repos__toggle').trigger('click')
    refresh.bump('sync')
    await flushPromises()
    expect(loads()).toBe(2)
  })

  it('Esc e o clique fora fecham o painel', async () => {
    await mountMenu()
    const store = useRepoIssuesStore()

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(store.open).toBe(false)

    store.openPanel()
    await flushPromises()
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(store.open).toBe(false)
  })
})

describe('RepoIssuesMenu por projeto do Bitbucket', () => {
  it('segmenta pelos projetos, com "Outros" no fim, e em "Todos" agrupa os repos', async () => {
    // WeON: a WAI-9224 está em dois repos dele e conta uma vez só.
    const { wrapper } = await mountMenu()

    expect(wrapper.findAll('.repos__segment').map((b) => b.text().replace(/\s+/g, ' '))).toEqual([
      'Todos',
      'OrganIA 4',
      'WeON 2',
      'Outros 1',
    ])
    expect(wrapper.findAll('.repos__group').map((g) => g.text())).toEqual(['OrganIA', 'WeON', 'Outros'])
  })

  it('escolher um projeto mostra só os repos dele, e a escolha fica lembrada', async () => {
    const { wrapper } = await mountMenu()

    await wrapper.find('.repos__segment[data-project="WEON"]').trigger('click')

    expect(wrapper.findAll('.repos__repo').map((b) => b.attributes('data-slug'))).toEqual(['supervisor-web', 'weaction-api'])
    expect(wrapper.find('.repos__repo--on').attributes('data-slug')).toBe('supervisor-web')
    expect(wrapper.findAll('.repos__group')).toHaveLength(0)
    expect(localStorage.getItem('sprintai.repoIssues.project')).toBe('WEON')
  })

  it('projeto lembrado que saiu do sync volta para "Todos"', async () => {
    localStorage.setItem('sprintai.repoIssues.project', 'DG')
    const { wrapper } = await mountMenu()

    expect(useRepoIssuesStore().activeProject).toBe('*')
    expect(wrapper.find('.repos__segment--on').text()).toBe('Todos')
  })
})

describe('TopbarTip', () => {
  it('mostra o atalho como teclas e, desativado, só o rótulo', () => {
    const wrapper = mount(TopbarTip, {
      props: {
        lines: [
          { label: 'Buscar lembretes', combo: 'Ctrl+Shift+L' },
          { label: 'Novo lembrete com a seleção', combo: null },
        ],
      },
      slots: { default: '<button type="button">x</button>' },
    })

    const lines = wrapper.findAll('.tip__line')
    expect(lines[0].findAll('kbd').map((k) => k.text())).toEqual(['Ctrl', 'Shift', 'L'])
    expect(lines[1].text()).toBe('Novo lembrete com a seleção')
    expect(lines[1].find('kbd').exists()).toBe(false)
    expect(wrapper.find('.tip__detail').exists()).toBe(false)
  })
})
