import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import HomeView from '@/views/HomeView.vue'
import SprintProgress from '@/components/home/SprintProgress.vue'
import SprintTimeline from '@/components/home/SprintTimeline.vue'
import { routes } from '@/router/routes'
import { useNotesStore } from '@/stores/notes'
import { useRealtimeStore } from '@/stores/realtime'

function json(status, body) {
  return {
    ok: status < 400,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => structuredClone(body),
    text: async () => '',
  }
}

const issue = (key, extra = {}) => ({
  key,
  summary: `Resumo ${key}`,
  issue_type: 'Tarefa',
  status: 'Disponivel para análise',
  status_category: 'new',
  priority: 'Medium',
  story_points: null,
  due_date: null,
  parent_key: null,
  parent_summary: null,
  sprint_name: null,
  sprint_state: null,
  updated_at: '2026-09-14T10:00:00Z',
  resolved_at: null,
  open_points: 0,
  url: `https://weon.atlassian.net/browse/${key}`,
  pr: null,
  ...extra,
})

const HOME = {
  today: '2026-09-14',
  timezone: 'America/Sao_Paulo',
  filtered_by_assignee: true,
  week_start: '2026-09-14',
  week_end: '2026-09-20',
  sprints: [
    {
      sprint_id: 3995,
      name: 'Sprint 73 - Growth',
      state: 'active',
      squad: 'Growth',
      start: '2026-09-09',
      end: '2026-09-11',
      real: 0.4,
      expected: 1,
      overdue_active: true,
      issue_count: 3,
      done_count: 1,
      story_points: 9,
      updates: [
        {
          key: 'WAI-1',
          summary: 'Endpoint da coleta',
          status: 'Em Review',
          status_category: 'indeterminate',
          story_points: 5,
          url: 'https://weon.atlassian.net/browse/WAI-1',
          kind: 'status',
          source: 'jira',
          title: 'Em Review',
          actor_name: 'Felipe',
          occurred_at: '2026-09-14T13:00:00Z',
          event_count: 2,
        },
        {
          key: 'WAI-3',
          summary: 'Tela da coleta',
          status: 'Em Desenvolvimento',
          status_category: 'indeterminate',
          story_points: null,
          url: 'https://weon.atlassian.net/browse/WAI-3',
          kind: 'pr_approved',
          source: 'bitbucket',
          title: 'WAI-3 ajusta a tela',
          actor_name: 'Revisor',
          occurred_at: '2026-09-13T18:00:00Z',
          event_count: 1,
        },
      ],
    },
  ],
  pending: {
    overdue: [issue('WAI-4', { due_date: '2026-09-01' })],
    due: [issue('WAI-5', { due_date: '2026-09-18' })],
    slicing: [issue('WAI-6', { summary: 'Analisar e fatiar a: Relatórios' })],
    without_sprint: [],
    total: 5,
  },
  reminders: [
    {
      id: 1,
      title: 'Venceu e não vi',
      body: '',
      color: 'yellow',
      tags: [],
      pinned: false,
      archived: false,
      remind_at: '2026-09-13T09:00:00-03:00',
      reminded_at: null,
      reminder_due: true,
      created_at: '2026-09-13T08:00:00Z',
      updated_at: '2026-09-13T08:00:00Z',
      issues: [{ key: 'WAI-1' }],
      rank: null,
    },
  ],
}

const segment = (status, stage, color, start, end) => ({
  status,
  stage_id: stage,
  color,
  start,
  end,
})

const timelineIssue = (key, extra = {}) => ({
  key,
  summary: `Resumo ${key}`,
  issue_type: 'Tarefa',
  status: 'Em Desenvolvimento',
  status_category: 'indeterminate',
  story_points: 5,
  assignee_name: 'Dev',
  url: `https://weon.atlassian.net/browse/${key}`,
  due_date: null,
  resolved_at: null,
  sprint_id: 3995,
  start: '2026-09-09T12:00:00Z',
  // Fim no futuro (sprint 74): é o caso em que a barra tem trecho de projeção.
  end: '2026-09-18T03:00:00Z',
  projected: true,
  started: true,
  progress: { value: 0.4, source: 'status', stage_id: 'desenvolvimento', stage_label: 'Desenvolvimento', stage_color: '#2f7cf6', done: null, total: null },
  segments: [segment('Em Desenvolvimento', 'desenvolvimento', '#2f7cf6', '2026-09-09T12:00:00Z', '2026-09-18T03:00:00Z')],
  pr: null,
  ...extra,
})

const TIMELINE = {
  today: '2026-09-14',
  timezone: 'America/Sao_Paulo',
  start: '2026-09-09',
  end: '2026-09-18',
  sprints: [
    { id: 3995, name: 'Sprint 73 - Growth', state: 'active', squad: 'Growth', start: '2026-09-09', end: '2026-09-11', overdue_active: true, current: false },
    { id: 3997, name: 'Sprint 74 - Growth', state: 'future', squad: 'Growth', start: '2026-09-14', end: '2026-09-18', overdue_active: false, current: true },
  ],
  groups: [
    {
      key: 'WAI-100',
      summary: 'Coleta consolidada',
      issue_type: 'Épico',
      url: 'https://weon.atlassian.net/browse/WAI-100',
      progress: 0.6,
      issues: [
        timelineIssue('WAI-1'),
        timelineIssue('WAI-2', {
          status: 'Concluído',
          status_category: 'done',
          resolved_at: '2026-09-10T20:00:00Z',
          end: '2026-09-10T20:00:00Z',
          projected: false,
          progress: { value: 1, source: 'status', stage_id: 'concluido', stage_label: 'Concluído', stage_color: '#10b981', done: null, total: null },
          segments: [segment('Concluído', 'concluido', '#10b981', '2026-09-09T12:00:00Z', '2026-09-10T20:00:00Z')],
        }),
      ],
    },
    {
      key: null,
      summary: 'Sem pai',
      issue_type: null,
      url: null,
      progress: 0,
      issues: [timelineIssue('WAI-3', { started: false })],
    },
  ],
  links: [{ source: 'WAI-1', target: 'WAI-3' }],
}

const FEED = {
  events: [
    {
      id: 3,
      source: 'jira',
      kind: 'comment',
      issue_key: 'WAI-1',
      issue_summary: 'Endpoint da coleta',
      issue_status: 'Em Desenvolvimento',
      issue_url: 'https://weon.atlassian.net/browse/WAI-1',
      repo_slug: null,
      pr_id: null,
      pr_url: null,
      actor_name: 'Outro Dev',
      actor_is_me: false,
      occurred_at: '2026-09-14T13:00:00Z',
      title: 'Olha isso aqui',
      detail: {},
    },
    {
      id: 2,
      source: 'bitbucket',
      kind: 'pr_approved',
      issue_key: 'WAI-1',
      issue_summary: 'Endpoint da coleta',
      issue_status: 'Em Desenvolvimento',
      issue_url: 'https://weon.atlassian.net/browse/WAI-1',
      repo_slug: 'monitoria',
      pr_id: 7,
      pr_url: 'https://bitbucket.org/weonrepo/monitoria/pull-requests/7',
      actor_name: 'Revisor',
      actor_is_me: false,
      occurred_at: '2026-09-13T18:00:00Z',
      title: 'WAI-1 ajusta coleta',
      detail: { url: 'https://bitbucket.org/weonrepo/monitoria/pull-requests/7' },
    },
    {
      id: 1,
      source: 'jira',
      kind: 'status',
      issue_key: 'WAI-1',
      issue_summary: 'Endpoint da coleta',
      issue_status: 'Em Desenvolvimento',
      issue_url: 'https://weon.atlassian.net/browse/WAI-1',
      repo_slug: null,
      pr_id: null,
      pr_url: null,
      actor_name: 'Matheus',
      actor_is_me: true,
      occurred_at: '2026-09-12T10:00:00Z',
      title: 'Em Desenvolvimento',
      detail: { from: 'Disponivel para análise', to: 'Em Desenvolvimento' },
    },
  ],
  next_cursor: 'cursor-2',
}

let calls
function routeFetch({ home = HOME, timeline = TIMELINE, feed = FEED } = {}) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      calls.push({ method: init.method ?? 'GET', url })
      if (url.startsWith('/api/home/timeline')) return json(200, timeline)
      if (url.startsWith('/api/home')) return json(200, home)
      if (url.startsWith('/api/activity')) return json(200, feed)
      // O stream fica de fora dos testes de tela: o store cuida dele à parte.
      if (url.startsWith('/api/events')) return { ok: false, status: 503, headers: new Headers(), json: async () => ({}), text: async () => '' }
      if (url.startsWith('/api/notes')) return json(200, { items: [], total: 0 })
      if (url.startsWith('/api/connections')) return json(200, { jira: { configured: true }, bitbucket: { configured: true } })
      if (url.startsWith('/api/sync')) return json(200, { last_success_at: '2026-09-14T12:00:00Z', bitbucket: { repo_slugs: ['monitoria'] } })
      return json(404, { detail: 'fora do teste' })
    }),
  )
}

async function mountHome(path = '/') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const wrapper = mount(HomeView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  useRealtimeStore().disconnect()
  vi.unstubAllGlobals()
})

describe('HomeView', () => {
  it('carrega Home, timeline e feed com o fuso do navegador', async () => {
    routeFetch()
    await mountHome()

    expect(calls.some((c) => /^\/api\/home\?tz=/.test(c.url))).toBe(true)
    expect(calls.some((c) => /^\/api\/home\/timeline\?tz=.*include_next=true/.test(c.url))).toBe(true)
    expect(calls.some((c) => c.url.startsWith('/api/activity?limit=25'))).toBe(true)
  })

  it('mostra a sprint vencida com o real, o esperado e o aviso', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const sprint = wrapper.find('[data-sprint="3995"]')

    expect(sprint.find('.sprint__name').text()).toBe('Sprint 73 - Growth')
    expect(sprint.find('.sprint__flag').text()).toContain('vencida')
    expect(sprint.find('.sprint__value').text()).toBe('40%')
    expect(sprint.find('.sprint__fill').attributes('style')).toContain('width: 40%')
    expect(sprint.find('.sprint__expected').attributes('style')).toContain('left: 100%')
    // 40% contra 100% esperado: a barra avisa, não só informa.
    expect(sprint.find('.sprint__fill').attributes('data-behind')).toBe('true')
    expect(sprint.find('.sprint__meta').text()).toContain('1/3 tarefas')
  })

  it('a sprint aponta para a árvore dela', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const link = wrapper.find('[data-sprint="3995"] .sprint__name')

    expect(link.text()).toContain('Sprint 73 - Growth')
    expect(link.attributes('href')).toBe('/sprints?sprint=3995')
  })

  it('mostra a linha das tarefas que mexeram, com contagem e autor', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const cards = wrapper.findAll('[data-sprint="3995"] .update')

    expect(cards.map((c) => c.attributes('data-key'))).toEqual(['WAI-1', 'WAI-3'])
    expect(cards[0].find('.update__count').text()).toBe('2')
    expect(cards[0].text()).toContain('Felipe')
    expect(cards[0].text()).toContain('mudou o status para')
    // Uma mexida só não ganha contador.
    expect(cards[1].find('.update__count').exists()).toBe(false)
    expect(cards[1].text()).toContain('Revisor')
  })

  it('clicar numa tarefa mexida abre o painel dela', async () => {
    routeFetch()
    const { wrapper, router } = await mountHome()

    await wrapper.findAll('.update__btn')[1].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.tarefa).toBe('WAI-3')
  })

  it('sem sprint com trabalho meu em aberto, explica em vez de sumir', async () => {
    routeFetch({ home: { ...HOME, sprints: [] } })
    const { wrapper } = await mountHome()

    expect(wrapper.find('.sprints__empty').text()).toContain('tarefa sua em aberto')
    expect(wrapper.findAll('.sprint')).toHaveLength(0)
  })

  it('pendências mostram só os blocos com item e o resto fica na Semana', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const pending = wrapper.find('[data-block="pending"]')

    expect(pending.findAll('.pending__sub').map((h) => h.text())).toEqual([
      'Atrasadas 1',
      'Prazo nesta semana 1',
      'Analisar e fatiar 1',
    ])
    expect(pending.findAll('.wrow').map((r) => r.attributes('data-key'))).toEqual(['WAI-4', 'WAI-5', 'WAI-6'])
    expect(pending.find('.pending__more').text()).toContain('e mais 2')
  })

  it('feed vem agrupado por dia, do mais novo para o mais antigo', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const feed = wrapper.find('[data-block="activity"]')

    expect(feed.findAll('.feed__day').map((d) => d.text())).toEqual(['Hoje', 'Ontem', expect.stringMatching(/sáb|sábado/)])
    expect(feed.findAll('.event').map((e) => e.attributes('data-kind'))).toEqual(['comment', 'pr_approved', 'status'])
    expect(feed.findAll('.event')[0].text()).toContain('Outro Dev')
    // O que fui eu que fiz aparece como "Você".
    expect(feed.findAll('.event')[2].text()).toContain('Você')
    expect(feed.findAll('.event')[1].find('.event__repo').text()).toBe('monitoria#7')
    expect(feed.find('.feed__more').exists()).toBe(true)
  })

  it('filtros do feed refazem a chamada e a paginação usa o cursor', async () => {
    routeFetch()
    const { wrapper } = await mountHome()

    await wrapper.findAll('.feed__chip')[2].trigger('click')
    await flushPromises()
    expect(calls.at(-1).url).toContain('source=bitbucket')

    await wrapper.findAll('.feed__chip')[3].trigger('click')
    await flushPromises()
    expect(calls.at(-1).url).toContain('only_others=true')

    await wrapper.find('.feed__more').trigger('click')
    await flushPromises()
    expect(calls.at(-1).url).toContain('cursor=cursor-2')
  })

  it('clicar num evento abre o painel da tarefa na aba certa', async () => {
    routeFetch()
    const { wrapper, router } = await mountHome()

    await wrapper.findAll('.event__main')[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tarefa).toBe('WAI-1')

    await wrapper.findAll('.event__main')[1].trigger('click')
    await flushPromises()
    // Evento de PR pede a aba de PRs do painel.
    expect(wrapper.vm).toBeTruthy()
  })

  it('lembretes relevantes abrem o editor e podem ser concluídos', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const block = wrapper.find('[data-block="reminders"]')

    expect(block.findAll('.reminder').map((r) => r.attributes('data-state'))).toEqual(['due'])
    expect(block.find('.reminder__issue').text()).toBe('WAI-1')

    await block.find('.reminder__ack').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/notes/1/reminder/ack')).toBe(true)

    await block.find('.reminder__main').trigger('click')
    expect(useNotesStore().editor.draft.id).toBe(1)
  })

  it('avisa quando a conexão não tem accountId', async () => {
    routeFetch({ home: { ...HOME, filtered_by_assignee: false } })
    const { wrapper } = await mountHome()
    expect(wrapper.find('.home__warn').exists()).toBe(true)
  })

  it('recarrega quando o stream avisa que chegou atividade', async () => {
    routeFetch()
    const { wrapper } = await mountHome()
    const before = calls.filter((c) => c.url.startsWith('/api/activity')).length

    useRealtimeStore().record('activity.new', { count: 2 })
    await flushPromises()

    expect(calls.filter((c) => c.url.startsWith('/api/activity')).length).toBe(before + 1)
    expect(wrapper.find('.home__stream').text()).toContain('sem stream')
  })
})

describe('SprintTimeline', () => {
  beforeEach(() => vi.useFakeTimers({ now: new Date('2026-09-14T15:00:00Z') }))
  afterEach(() => vi.useRealTimers())

  function mountTimeline(timeline = TIMELINE) {
    return mount(SprintTimeline, { props: { timeline } })
  }

  it('desenha faixa de sprints, meses, dias e o marcador de hoje', () => {
    const wrapper = mountTimeline()

    expect(wrapper.findAll('.tl__sprint').map((s) => s.text())).toEqual([
      'Sprint 73 - Growth',
      'Sprint 74 - Growth',
    ])
    expect(wrapper.findAll('.tl__sprint')[0].attributes('data-overdue')).toBe('true')
    expect(wrapper.findAll('.tl__sprint')[1].attributes('data-current')).toBe('true')
    expect(wrapper.findAll('.tl__month').map((m) => m.text())).toEqual(['SET'])
    // 09/09 a 18/09 = 10 dias.
    expect(wrapper.findAll('.tl__daynum')).toHaveLength(10)
    // 12 e 13/09 são sábado e domingo.
    expect(wrapper.findAll('.tl__day[data-weekend]')).toHaveLength(2)
    expect(wrapper.find('.tl__today').exists()).toBe(true)
  })

  it('agrupa por pai, com uma linha por tarefa e as barras segmentadas', () => {
    const wrapper = mountTimeline()
    const rows = wrapper.findAll('.tl__row')

    expect(rows.map((r) => r.attributes('data-type'))).toEqual([
      'group',
      'issue',
      'issue',
      'group',
      'issue',
    ])
    const done = rows[2]
    expect(done.find('.tl__key').attributes('data-done')).toBe('true')
    expect(done.find('.tl__bar').attributes('data-projected')).toBeUndefined()
    expect(done.find('.tl__segment').attributes('style')).toContain('rgb(16, 185, 129)')

    const emAndamento = rows[1]
    expect(emAndamento.find('.tl__bar').attributes('data-projected')).toBe('true')
    expect(emAndamento.find('.tl__projection').exists()).toBe(true)
    expect(emAndamento.find('.tl__status').text()).toBe('Desenvolvimento')
  })

  it('recolher um grupo esconde as tarefas e as setas de bloqueio delas', async () => {
    const wrapper = mountTimeline()
    expect(wrapper.findAll('.tl__link')).toHaveLength(1)

    await wrapper.findAll('.tl__toggle')[0].trigger('click')

    expect(wrapper.findAll('.tl__row').map((r) => r.attributes('data-type'))).toEqual([
      'group',
      'group',
      'issue',
    ])
    // A ponta de origem sumiu: a seta não é desenhada solta.
    expect(wrapper.findAll('.tl__link')).toHaveLength(0)
  })

  it('emite abertura da tarefa e do pai', async () => {
    const wrapper = mountTimeline()

    await wrapper.findAll('.tl__name')[0].trigger('click')
    await wrapper.findAll('.tl__name')[1].trigger('click')

    expect(wrapper.emitted('open')).toEqual([['WAI-100'], ['WAI-1']])
  })

  it('sem tarefa nenhuma, explica em vez de desenhar uma grade vazia', () => {
    const wrapper = mountTimeline({ ...TIMELINE, groups: [], links: [] })
    expect(wrapper.find('.tl__empty').text()).toContain('Nenhuma tarefa sua')
  })
})

describe('SprintProgress', () => {
  const SPRINT = HOME.sprints[0]

  function mountProgress(sprints = [SPRINT]) {
    return mount(SprintProgress, { props: { sprints }, global: { stubs: { RouterLink: true } } })
  }

  it('o card da tarefa mexida pede a aba certa do painel', async () => {
    const wrapper = mountProgress()

    await wrapper.findAll('.update__btn')[0].trigger('click')
    await wrapper.findAll('.update__btn')[1].trigger('click')

    // status → Detalhes; aprovação de PR → PRs.
    expect(wrapper.emitted('open')).toEqual([
      ['WAI-1', 'detalhes'],
      ['WAI-3', 'prs'],
    ])
  })

  it('sprint sem mexida de ninguém não mostra a linha', () => {
    const wrapper = mountProgress([{ ...SPRINT, updates: [] }])

    expect(wrapper.find('.updates').exists()).toBe(false)
    expect(wrapper.find('.sprint__track').exists()).toBe(true)
  })

  it('sprint em dia não ganha o aviso de vencida', () => {
    const wrapper = mountProgress([
      { ...SPRINT, overdue_active: false, real: 0.5, expected: 0.4, updates: [] },
    ])

    expect(wrapper.find('.sprint__flag').exists()).toBe(false)
    // Na frente do esperado: barra normal, sem aviso.
    expect(wrapper.find('.sprint__fill').attributes('data-behind')).toBeUndefined()
  })
})
