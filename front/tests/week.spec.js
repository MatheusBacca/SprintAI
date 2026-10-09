import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import WeekView from '@/views/WeekView.vue'
import { routes } from '@/router/routes'
import { useNotesStore } from '@/stores/notes'
import { isoDay, shiftDay } from '@/stores/week'

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => structuredClone(body), text: async () => '' }
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
  updated_at: '2026-09-15T10:00:00Z',
  resolved_at: null,
  open_points: 0,
  url: `https://weon.atlassian.net/browse/${key}`,
  pr: { status: 'sem_pr', status_label: 'Sem PR', pr_count: 0, open_pr_count: 0, build_failed: false },
  ...extra,
})

const note = (id, remindAt, extra = {}) => ({
  id,
  title: `Lembrete ${id}`,
  body: '',
  color: 'yellow',
  tags: [],
  pinned: false,
  archived: false,
  remind_at: remindAt,
  reminded_at: null,
  reminder_due: false,
  created_at: '2026-09-14T10:00:00Z',
  updated_at: '2026-09-14T10:00:00Z',
  issues: [],
  rank: null,
  ...extra,
})

const REVIEW = { id: 'review', label: 'Review', color: '#f59e0b' }
const DONE = { id: 'concluido', label: 'Concluído', color: '#10b981' }
const DEV = { id: 'desenvolvimento', label: 'Desenvolvimento', color: '#2f7cf6' }
const move = (status, stage, at, extra = {}) => ({ status, stage, at, author_name: 'Matheus Bacca', by_me: true, ...extra })
const STAGES = [
  { id: 'analise', label: 'Análise', color: '#94a3b8' },
  DEV,
  REVIEW,
  { id: 'testes', label: 'Testes', color: '#8a4fff' },
  DONE,
]
const dayIssue = (key, outcome, [fromStatus, fromStage], moves) => ({
  key,
  summary: `Resumo ${key}`,
  issue_type: 'Tarefa',
  story_points: 3,
  from_status: fromStatus,
  from_stage: fromStage,
  moves,
  outcome,
})

const SUMMARY = {
  stages: STAGES,
  delivery_stage: REVIEW,
  days: [
    {
      day: '2026-09-14',
      issues: [
        dayIssue('WAI-1', 'entregue', ['Em Review', REVIEW], [move('Concluído', DONE, '2026-09-14T15:00:00Z', { by_me: false, author_name: 'Poliane Melo' })]),
        dayIssue('WAI-3', 'entregue', ['Em Desenvolvimento', DEV], [
          move('DISPONIVEL PARA REVIEW', REVIEW, '2026-09-14T16:00:00Z'),
          move('Em Review', REVIEW, '2026-09-14T17:00:00Z', { by_me: false, author_name: 'Felipe Queirolo' }),
        ]),
        dayIssue('WAI-2', 'avancou', ['Disponivel para análise', STAGES[0]], [move('Em Desenvolvimento', DEV, '2026-09-14T12:00:00Z')]),
      ],
    },
    {
      day: '2026-09-15',
      issues: [
        dayIssue('WAI-6', 'voltou', ['Em Review', REVIEW], [move('AJUSTE', DEV, '2026-09-15T12:00:00Z', { by_me: null, author_name: 'Rodrigo Vianna' })]),
        // Status fora de Configurações › Progresso: sem etapa, vai para "Outros status".
        dayIssue('WAI-7', 'mexeu', ['Em Desenvolvimento', DEV], [move('Cruzeiro', null, '2026-09-15T13:00:00Z')]),
      ],
    },
    { day: '2026-09-16', issues: [] },
  ],
}

const WEEK = {
  start: '2026-09-14',
  end: '2026-09-20',
  today: '2026-09-16',
  timezone: 'America/Sao_Paulo',
  filtered_by_assignee: true,
  without_sprint: [
    issue('WAI-2', { sprint_name: 'Sprint 72', sprint_state: 'closed', open_points: 2 }),
    issue('WAI-1', { parent_summary: 'Épico de integrações', story_points: 3 }),
  ],
  due: [issue('WAI-3', { due_date: '2026-09-18', sprint_name: 'Sprint 73', sprint_state: 'active' }), issue('WAI-7', { due_date: '2026-09-16', status_category: 'done', status: 'Concluído' })],
  overdue: [issue('WAI-6', { due_date: '2026-09-01' })],
  slicing: [
    issue('WAI-8', { summary: 'Analisar e fatiar a: Nova regra', status: 'Em Desenvolvimento', status_category: 'indeterminate' }),
    issue('WAI-9', { summary: 'Analisar e Fatiar - Concluído', status: 'Concluído', status_category: 'done' }),
  ],
  reminders: [note(1, '2026-09-16T12:00:00-03:00', { reminder_due: true }), note(2, '2026-09-19T09:30:00-03:00', { issues: [{ key: 'WAI-1' }] })],
  pending_reminders: [note(3, '2026-09-08T09:00:00-03:00', { reminder_due: true })],
  summary: SUMMARY,
}

let calls
function routeFetch(week = WEEK) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      calls.push({ method: init.method ?? 'GET', url })
      if (url.startsWith('/api/week')) return json(200, week)
      if (url.startsWith('/api/notes/')) return json(200, note(1, null))
      return json(404, { detail: 'fora do teste' })
    }),
  )
}

async function mountWeek(path = '/semana') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const wrapper = mount(WeekView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

describe('datas da semana', () => {
  it('soma dias sem escorregar e formata no fuso local', () => {
    expect(shiftDay('2026-09-14', 7)).toBe('2026-09-21')
    expect(shiftDay('2026-01-05', -7)).toBe('2025-12-29')
    expect(isoDay(new Date(2026, 8, 4, 23, 30))).toBe('2026-09-04')
  })
})

describe('WeekView', () => {
  it('carrega a semana com o fuso do navegador e mostra os quatro blocos', async () => {
    routeFetch()
    const { wrapper } = await mountWeek()

    expect(calls[0].url).toMatch(/^\/api\/week\?tz=/)
    expect(wrapper.find('.week__label').text()).toBe('Esta semana')
    expect(wrapper.findAll('.block').map((b) => b.attributes('data-block'))).toEqual(['due', 'reminders', 'slicing', 'without-sprint', 'summary'])

    const without = wrapper.find('[data-block="without-sprint"]')
    expect(without.findAll('.wrow').map((r) => r.attributes('data-key'))).toEqual(['WAI-2', 'WAI-1'])
    expect(without.find('.wrow__leftover').text()).toContain('sobrou da Sprint 72')
    expect(without.find('.wrow__points').text()).toBe('2')
    expect(without.findAll('.wrow')[1].text()).toContain('Épico de integrações')

    const due = wrapper.find('[data-block="due"]')
    expect(due.findAll('.block__sub').map((h) => h.text())).toEqual(['Atrasadas 1', expect.stringMatching(/quarta/), expect.stringMatching(/sexta/)])
    expect(due.find('.block__sub[data-today]').text()).toMatch(/quarta/)
    expect(due.find('.wrow__due--late').exists()).toBe(true)
    expect(due.find('.wrow--done').attributes('data-key')).toBe('WAI-7')

    const slicing = wrapper.find('[data-block="slicing"]')
    expect(slicing.find('.block__title small').text()).toBe('1')
    expect(slicing.find('.block__sub').text()).toBe('Concluídos nesta semana 1')
  })

  it('lembretes: pendentes de antes, por dia, concluir e abrir', async () => {
    routeFetch()
    const { wrapper } = await mountWeek()
    const block = wrapper.find('[data-block="reminders"]')

    expect(block.findAll('.block__sub')[0].text()).toBe('Pendentes de antes 1')
    expect(block.findAll('.reminder').map((r) => [r.attributes('data-id'), r.attributes('data-state')])).toEqual([
      ['3', 'due'],
      ['1', 'due'],
      ['2', 'upcoming'],
    ])
    expect(block.findAll('.reminder')[2].text()).toContain('WAI-1')

    await block.findAll('.reminder__ack')[1].trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/notes/1/reminder/ack')).toBe(true)
    // Escrita em lembrete recarrega a semana.
    expect(calls.filter((c) => c.url.startsWith('/api/week'))).toHaveLength(2)

    await block.findAll('.reminder__main')[2].trigger('click')
    expect(useNotesStore().editor.draft.id).toBe(2)
  })

  it('navega entre semanas pela URL e abre o painel da tarefa', async () => {
    routeFetch()
    const { wrapper, router } = await mountWeek()

    await wrapper.find('[aria-label="Próxima semana"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.dia).toBe('2026-09-21')
    expect(calls.at(-1).url).toMatch(/^\/api\/week\?day=2026-09-21&tz=/)

    await wrapper.find('[data-block="without-sprint"] .wrow__main').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ dia: '2026-09-21', tarefa: 'WAI-2' })
  })

  it('resumo em kanban: etapas em colunas, uma faixa por dia e só entregas', async () => {
    routeFetch()
    const { wrapper, router } = await mountWeek()
    const block = wrapper.find('[data-block="summary"]')
    const cell = (day, stage) => block.findAll('.board__cell').filter((c) => c.attributes('data-stage') === stage)[day]
    const keys = (el) => el.findAll('.scard').map((c) => c.attributes('data-key'))

    expect(block.find('.block__title small').text()).toBe('2')
    expect(block.find('.block__hint').text()).toContain('avançou até Review')
    // Só as etapas que receberam card na semana; Análise e Testes ficam de fora.
    expect(block.findAll('.board__col').map((c) => c.text())).toEqual(['Desenvolvimento 2', 'Review 1', 'Concluído 1', 'Outros status 1'])
    expect(block.findAll('.board__day').map((d) => d.find('strong').text())).toEqual(['segunda-feira', 'terça-feira', 'quarta-feira'])
    expect(block.find('.board__day[data-today]').text()).toMatch(/quarta/)
    expect(block.findAll('.board__day')[0].find('.board__delivered').text()).toBe('2 entregas')

    // A tarefa cai na coluna da etapa em que terminou o dia.
    expect(keys(cell(0, 'concluido'))).toEqual(['WAI-1'])
    expect(keys(cell(0, 'review'))).toEqual(['WAI-3'])
    expect(keys(cell(0, 'desenvolvimento'))).toEqual(['WAI-2'])
    expect(keys(cell(1, 'desenvolvimento'))).toEqual(['WAI-6'])
    expect(keys(cell(1, 'outros'))).toEqual(['WAI-7'])

    const card = (key) => block.find(`.scard[data-key="${key}"]`)
    expect(card('WAI-1').attributes('data-outcome')).toBe('entregue')
    expect(card('WAI-1').find('.scard__done').exists()).toBe(true)
    // Onde parou (com quem mexeu, quando não fui eu) e de onde veio.
    expect(card('WAI-1').find('.scard__status').text()).toBe('Concluído · Poliane')
    expect(card('WAI-1').find('.scard__from').text()).toBe('de Review')
    expect(card('WAI-3').find('.scard__status').text()).toBe('Em Review · Felipe')
    expect(card('WAI-3').find('.scard__from').text()).toBe('de Desenvolvimento')
    expect(card('WAI-2').find('.scard__status').text()).toBe('Em Desenvolvimento')
    expect(card('WAI-6').find('.scard__from').text()).toBe('voltou de Review')
    expect(card('WAI-6').find('.scard__status').text()).toBe('AJUSTE · Rodrigo')
    // O caminho inteiro do dia vai no title do card.
    const trail = card('WAI-3').find('.scard__main').attributes('title')
    expect(trail).toContain('Começou o dia em Em Desenvolvimento')
    expect(trail).toMatch(/DISPONIVEL PARA REVIEW \(você\)/)
    expect(trail).toMatch(/Em Review \(Felipe Queirolo\)/)
    expect(block.findAll('.board__none').map((p) => p.text())).toEqual(['Nenhuma tarefa sua mudou de status.'])

    await block.find('.block__action').trigger('click')
    expect(block.find('.block__action').attributes('aria-pressed')).toBe('true')
    expect(keys(block)).toEqual(['WAI-3', 'WAI-1'])
    // As colunas são da semana, não do filtro.
    expect(block.findAll('.board__col')).toHaveLength(4)
    expect(block.findAll('.board__none').map((p) => p.text())).toEqual(['Nenhuma entrega neste dia.', 'Nenhuma tarefa sua mudou de status.'])

    await card('WAI-3').find('.scard__main').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tarefa).toBe('WAI-3')
  })

  it('resumo: semana sem nenhuma mudança de status', async () => {
    routeFetch({ ...WEEK, summary: { stages: STAGES, delivery_stage: REVIEW, days: [{ day: '2026-09-14', issues: [] }, { day: '2026-09-15', issues: [] }] } })
    const { wrapper } = await mountWeek()
    const block = wrapper.find('[data-block="summary"]')

    expect(block.find('.block__empty').text()).toContain('Nenhuma tarefa sua mudou de status nesta semana')
    expect(block.find('.board').exists()).toBe(false)
    expect(block.find('.block__action').exists()).toBe(false)
  })

  it('outra semana, vazios e aviso sem accountId', async () => {
    routeFetch({
      ...WEEK,
      start: '2026-09-28',
      end: '2026-10-04',
      filtered_by_assignee: false,
      without_sprint: [],
      due: [],
      overdue: [],
      slicing: [],
      reminders: [],
      pending_reminders: [],
      summary: { stages: STAGES, delivery_stage: REVIEW, days: [] },
    })
    const { wrapper } = await mountWeek('/semana?dia=2026-09-30')

    expect(calls[0].url).toMatch(/^\/api\/week\?day=2026-09-30&tz=/)
    expect(wrapper.find('.week__label').text()).toBe('Daqui a 2 semanas')
    expect(wrapper.find('.week__warn').exists()).toBe(true)
    expect(wrapper.findAll('.block__empty')).toHaveLength(5)
    expect(wrapper.find('[data-block="summary"] .block__empty').text()).toBe('A semana ainda não começou.')

    await wrapper.find('[data-block="reminders"] .block__action').trigger('click')
    expect(useNotesStore().editor.draft.remind_at).toBe(new Date('2026-09-28T09:00:00').toISOString())
  })
})
