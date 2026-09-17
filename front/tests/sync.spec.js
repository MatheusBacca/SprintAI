import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import RepoPicker from '@/components/settings/RepoPicker.vue'
import SetupChecklist from '@/components/home/SetupChecklist.vue'
import SyncIndicator from '@/components/shell/SyncIndicator.vue'
import SettingsView from '@/views/SettingsView.vue'
import { routes } from '@/router/routes'
import { useSyncStore } from '@/stores/sync'

const NOW = new Date().toISOString()

const SCOPE = {
  enabled: true,
  interval_minutes: 5,
  jira: {
    board_ids: [144],
    squads: ['Growth'],
    include_unsquadded: true,
    closed_sprints_limit: 6,
    my_issues_lookback_days: 30,
    project_keys: ['WAI'],
    assignee_scope: 'mine',
  },
  bitbucket: { repo_slugs: [], initial_lookback_days: 60, full_sweep_minutes: 30, pr_scope: 'mine' },
}

const STATUS_OK = {
  running: false,
  last_run: { id: 1, trigger: 'scheduled', status: 'success', started_at: NOW, finished_at: NOW, stats: {}, errors: [] },
  last_success_at: NOW,
  counts: { issues: 2082, sprints_in_scope: 12, comments: 5199, links: 498, repositories: 0, pull_requests: 0, branches: 0 },
}

const REPOS = [
  { slug: 'monitoria', name: 'monitoria', project_name: 'OrganIA', updated_on: NOW },
  { slug: 'organia-configs', name: 'organia-configs', project_name: 'OrganIA', updated_on: NOW },
  { slug: 'supervisor-web', name: 'supervisor-web', project_name: 'Plataforma', updated_on: NOW },
]

const SPRINTS = [
  { id: 3995, name: 'Sprint 73 - Growth', state: 'active', squad: 'Growth', issue_count: 62 },
  { id: 2872, name: '🚨BUGS-ANALISADOS', state: 'future', squad: null, issue_count: 1184 },
]

function json(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  }
}

function routeFetch(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init) => {
      const key = `${init.method} ${url}`
      calls.push({ key, body: init.body ? JSON.parse(init.body) : undefined })
      const handler = routes[key]
      if (!handler) throw new Error(`fetch não mockado: ${key}`)
      return typeof handler === 'function' ? handler(init) : handler
    }),
  )
  return calls
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  vi.unstubAllGlobals()
  useSyncStore().stopPolling()
})

describe('RepoPicker', () => {
  it('agrupa por projeto e marca/desmarca projeto inteiro', async () => {
    routeFetch({ 'GET /api/bitbucket/repositories?limit=1000': json(200, REPOS) })
    const wrapper = mount(RepoPicker, { props: { modelValue: ['monitoria'] } })
    await flushPromises()

    const groups = wrapper.findAll('.picker__group')
    expect(groups.map((g) => g.find('strong').text())).toEqual(['OrganIA', 'Plataforma'])
    expect(groups[0].find('.picker__project .muted').text()).toBe('1/2')

    await groups[0].find('.picker__project input').trigger('change')
    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toEqual(['monitoria', 'organia-configs'])
  })

  it('filtra pelo texto e avisa de repositório escolhido que sumiu', async () => {
    routeFetch({ 'GET /api/bitbucket/repositories?limit=1000': json(200, REPOS) })
    const wrapper = mount(RepoPicker, { props: { modelValue: ['repo-apagado'] } })
    await flushPromises()

    await wrapper.find('input[type="search"]').setValue('super')
    expect(wrapper.findAll('.picker__slug').map((s) => s.text())).toEqual(['supervisor-web'])
    expect(wrapper.text()).toContain('Não encontrados no workspace: repo-apagado')
  })
})

describe('Configurações › Sincronização', () => {
  async function mountSync(extra = {}) {
    const calls = routeFetch({
      'GET /api/sync/scope': json(200, SCOPE),
      'GET /api/sync/sprints': json(200, SPRINTS),
      'GET /api/sync/status': json(200, STATUS_OK),
      'GET /api/connections': json(200, []),
      'GET /api/jira/boards?project_key=WAI': json(200, [
        { id: 144, name: 'Engenharia', type: 'scrum', project_key: 'WAI' },
        { id: 610, name: 'Platform', type: 'kanban', project_key: 'WAI' },
      ]),
      'GET /api/jira/boards/144/sprints?state=active,future,closed': json(200, {
        board_id: 144,
        supports_sprints: true,
        sprints: [
          { id: 1, name: 'Sprint 73 - Core', state: 'active', squad: 'Core' },
          { id: 2, name: 'Sprint 73 - Growth', state: 'active', squad: 'Growth' },
          { id: 3, name: '🛠️BUG-SUPORT', state: 'future', squad: null },
        ],
      }),
      'GET /api/bitbucket/repositories?limit=1000': json(200, REPOS),
      'PUT /api/sync/scope': (init) => json(200, JSON.parse(init.body)),
      ...extra,
    })
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/configuracoes?aba=sincronizacao')
    await router.isReady()
    const wrapper = mount(SettingsView, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()
    return { wrapper, calls }
  }

  it('abre a aba pela URL, lista só boards scrum e squads do board', async () => {
    const { wrapper } = await mountSync()

    expect(wrapper.find('.settings__tab--active').text()).toBe('Sincronização')
    expect(wrapper.findAll('select option').map((o) => o.text())).toEqual(['Engenharia (WAI · 144)'])
    expect(wrapper.findAll('.chip').map((c) => c.text().split(' ')[0])).toEqual(['Core', 'Growth'])
    expect(wrapper.find('.chip--on').text()).toContain('Growth')
    expect(wrapper.text()).toContain('🛠️BUG-SUPORT')
  })

  it('avisa do volume dos baldes e mostra contagem por sprint', async () => {
    const { wrapper } = await mountSync()

    expect(wrapper.text()).toContain('🚨BUGS-ANALISADOS (1184) concentram a maior parte das 1246 tarefas')
    expect(wrapper.findAll('.sprints tbody tr')).toHaveLength(2)
  })

  it('padrão é só o que é meu e dá para ampliar Jira e Bitbucket', async () => {
    const { wrapper, calls } = await mountSync()
    const [jiraGroup, prGroup] = wrapper.findAll('.segmented')

    expect(jiraGroup.find('.segmented__option--on').text()).toBe('Só as minhas')
    expect(prGroup.find('.segmented__option--on').text()).toBe('Só os meus')

    await jiraGroup.findAll('input')[1].setValue()
    await prGroup.findAll('input')[1].setValue()
    await wrapper.findAll('.sync-panel__actions .btn').at(-1).trigger('click')
    await flushPromises()

    const put = calls.find((c) => c.key === 'PUT /api/sync/scope')
    expect(put.body.jira.assignee_scope).toBe('all')
    expect(put.body.bitbucket.pr_scope).toBe('all')
  })

  it('salva repositórios escolhidos e squads no escopo', async () => {
    const { wrapper, calls } = await mountSync()
    const save = () => wrapper.findAll('.sync-panel__actions .btn').at(-1)

    expect(save().attributes('disabled')).toBeDefined() // nada mudou ainda

    await wrapper.findAll('.picker__repo input')[0].trigger('change')
    await wrapper.findAll('.chip input')[0].trigger('change') // marca Core
    await save().trigger('click')
    await flushPromises()

    const put = calls.find((c) => c.key === 'PUT /api/sync/scope')
    expect(put.body.bitbucket.repo_slugs).toEqual(['monitoria'])
    expect(put.body.jira.squads).toEqual(['Growth', 'Core'])
    expect(wrapper.text()).toContain('Escopo salvo')
  })
})

describe('SyncIndicator', () => {
  it('mostra há quanto tempo sincronizou e dispara ao clicar', async () => {
    const calls = routeFetch({
      'GET /api/sync/status': json(200, STATUS_OK),
      'POST /api/sync': json(202, { run_id: 2 }),
    })
    const wrapper = mount(SyncIndicator)
    await flushPromises()

    expect(wrapper.text()).toBe('Sincronizado agora mesmo')
    await wrapper.trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.key === 'POST /api/sync')).toBe(true)
  })

  it('sinaliza sync parcial com os erros no título', async () => {
    routeFetch({
      'GET /api/sync/status': json(200, {
        ...STATUS_OK,
        last_run: { ...STATUS_OK.last_run, status: 'partial', errors: [{ stage: 'bitbucket', message: 'Bitbucket: limite atingido' }] },
      }),
    })
    const wrapper = mount(SyncIndicator)
    await flushPromises()

    expect(wrapper.classes()).toContain('sync--warning')
    expect(wrapper.attributes('title')).toContain('limite atingido')
  })
})

describe('SetupChecklist', () => {
  it('lista os passos pendentes da configuração inicial', async () => {
    routeFetch({
      'GET /api/connections': json(200, [
        { provider: 'jira', configured: true, last_error: null, settings: {} },
        { provider: 'bitbucket', configured: false, settings: {} },
      ]),
      'GET /api/sync/scope': json(200, SCOPE),
    })
    const router = createRouter({ history: createMemoryHistory(), routes })
    const wrapper = mount(SetupChecklist, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('.setup__progress').text()).toBe('1/4')
    expect(wrapper.findAll('.setup__link').map((l) => l.text())).toEqual([
      'Conectar o Bitbucket',
      'Escolher repositórios e escopo',
      'Primeira sincronização',
    ])
  })
})
