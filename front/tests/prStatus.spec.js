import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import PrApprovalPanel from '@/components/settings/PrApprovalPanel.vue'
import { PR_STATUS, PR_STATUS_LEGEND, approvalsLabel, prStatusMeta } from '@/constants/prStatus'

// Mesmas chaves do enum PrStatus do back (services/pr_status.py).
const BACKEND_STATUSES = [
  'sem_pr',
  'branch_sem_pr',
  'ajustes_requisitados',
  'rascunho',
  'pr_aberta',
  'aprovada',
  'mergeada',
  'recusada',
  'substituida',
]

const PEOPLE = ['Ana Lima', 'Bruno Reis', 'Carla Dias', 'Davi Melo']

// O back manda quem revisa na ordem da barra antiga: aprovou, pediu ajuste, falta revisar.
const review = (approvals, reviewers, changes = 0, required = 1) => ({
  approvals,
  reviewers,
  changes_requested: changes,
  required,
  people: PEOPLE.slice(0, reviewers).map((name, i) => ({
    name,
    state: i < approvals ? 'approved' : i < approvals + changes ? 'changes_requested' : 'pending',
    account_id: `acc-${i}`,
    avatar_url: null,
  })),
})

describe('constantes de status de PR', () => {
  it('cobre todos os status do back', () => {
    expect(Object.keys(PR_STATUS).sort()).toEqual([...BACKEND_STATUSES].sort())
  })

  it('status desconhecido cai em Sem PR', () => {
    expect(prStatusMeta('xpto').label).toBe('Sem PR')
  })

  it('legenda segue a ordem de atenção do back', () => {
    expect(PR_STATUS_LEGEND).toEqual(BACKEND_STATUSES.slice(0, 7))
  })

  it('conta as aprovações no singular só com um revisor', () => {
    expect(approvalsLabel(review(0, 1))).toBe('0/1 aprovação')
    expect(approvalsLabel(review(1, 2))).toBe('1/2 aprovações')
  })
})

describe('PrStatusBadge', () => {
  it('mostra rótulo, cor do token e contador quando há mais de um PR', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'ajustes_requisitados', prCount: 2 } })

    expect(wrapper.text()).toContain('Ajustes requisitados')
    expect(wrapper.find('.pr-badge__count').text()).toBe('2 PRs')
    expect(wrapper.attributes('style')).toContain('--badge-color: var(--pr-changes)')
    expect(wrapper.attributes('title')).toBe('Ajustes requisitados · 2 PRs')
  })

  it('não mostra contador com um PR e sinaliza build falhando', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'pr_aberta', prCount: 1, buildFailed: true } })

    expect(wrapper.find('.pr-badge__count').exists()).toBe(false)
    expect(wrapper.find('[aria-label="build falhando"]').exists()).toBe(true)
    expect(wrapper.attributes('title')).toBe('PR aberta · build falhando')
  })

  it('com a review andando mostra só as fotos de quem revisa, no lugar da barra e do N/X', () => {
    // Caso real WAI-8791 com a regra "Todos": um dos dois revisores aprovou.
    const photo = 'https://avatar-management.example/AL-2.png'
    const r = review(1, 2, 0, 2)
    r.people[0].avatar_url = photo
    const wrapper = mount(PrStatusBadge, { props: { status: 'pr_aberta', review: r } })

    expect(wrapper.classes()).toContain('pr-badge--review')
    expect(wrapper.find('.pr-badge__bar').exists()).toBe(false)
    const faces = wrapper.findAll('.faces__face')
    expect(faces.map((f) => f.attributes('data-state'))).toEqual(['approved', 'pending'])
    expect(faces.map((f) => f.attributes('title'))).toEqual(['Ana Lima — aprovou', 'Bruno Reis — falta revisar'])
    expect(faces[0].find('img').attributes()).toMatchObject({ src: photo, referrerpolicy: 'no-referrer' })
    // Sem foto, as iniciais — e nada de contagem à vista.
    expect(faces[1].find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('BR')
    expect(wrapper.attributes('title')).toBe(
      'PR aberta · 1/2 aprovações · Ana Lima aprovou, Bruno Reis falta revisar · falta 1 aprovação',
    )
  })

  it('foto que não carrega cai para as iniciais, e só https vira src', async () => {
    const r = review(1, 2)
    r.people[0].avatar_url = 'https://avatar-management.example/x.png'
    r.people[1].avatar_url = 'javascript:alert(1)'
    const wrapper = mount(PrStatusBadge, { props: { status: 'aprovada', review: r } })

    expect(wrapper.findAll('img')).toHaveLength(1)
    await wrapper.find('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('ALBR')
  })

  it('pinta quem pediu ajuste e conta no title', () => {
    const wrapper = mount(PrStatusBadge, {
      props: { status: 'ajustes_requisitados', review: review(1, 4, 2, 2) },
    })

    expect(wrapper.findAll('.faces__face').map((f) => f.attributes('data-state'))).toEqual([
      'approved', 'changes_requested', 'changes_requested', 'pending',
    ])
    expect(wrapper.attributes('title')).toContain('1/4 aprovações')
    expect(wrapper.attributes('title')).toContain('2 pedidos de ajuste · falta 1 aprovação')
  })

  it('aprovada pela regra não diz que falta aprovação', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'aprovada', review: review(1, 2, 0, 1) } })

    expect(wrapper.attributes('title')).toBe('Aprovada · 1/2 aprovações · Ana Lima aprovou, Bruno Reis falta revisar')
  })

  it('review sem a lista de quem revisa (resposta antiga) fica com o N/X', () => {
    const { people, ...semFotos } = review(1, 2)
    expect(people).toHaveLength(2)
    const wrapper = mount(PrStatusBadge, { props: { status: 'pr_aberta', review: semFotos } })

    expect(wrapper.text()).toBe('1/2')
    expect(wrapper.find('.faces').exists()).toBe(false)
  })

  it.each(['mergeada', 'rascunho', 'sem_pr'])('fora da review (%s) o badge segue só com o rótulo', (status) => {
    const wrapper = mount(PrStatusBadge, { props: { status, review: review(1, 2) } })

    expect(wrapper.text()).toBe(PR_STATUS[status].label)
    expect(wrapper.classes()).not.toContain('pr-badge--review')
    expect(wrapper.find('.faces').exists()).toBe(false)
  })

  it('sem revisor não há fotos', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'pr_aberta', review: review(0, 0) } })

    expect(wrapper.text()).toBe('PR aberta')
    expect(wrapper.find('.faces').exists()).toBe(false)
  })
})

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

describe('PrApprovalPanel', () => {
  let calls

  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    let saved = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, init = {}) => {
        const body = init.body ? JSON.parse(init.body) : undefined
        calls.push({ method: init.method ?? 'GET', url, body })
        if (init.method === 'PUT') saved = body.min_percent
        return json(200, { min_percent: saved })
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  function statuses(wrapper) {
    return wrapper.findAll('.approval__examples li').map((li) => li.attributes('data-status'))
  }

  it('começa na regra de antes e a prévia segue a regra escolhida antes de salvar', async () => {
    const wrapper = mount(PrApprovalPanel)
    await flushPromises()

    const selected = wrapper.find('.segmented__option--on')
    expect(selected.text()).toBe('Uma aprovação')
    expect(statuses(wrapper)).toEqual(['aprovada', 'aprovada', 'ajustes_requisitados'])

    await wrapper.findAll('input[type="radio"]')[2].setValue()
    expect(wrapper.find('.segmented__option--on').text()).toBe('Todos')
    expect(statuses(wrapper)).toEqual(['pr_aberta', 'pr_aberta', 'ajustes_requisitados'])
    // A prévia tem as fotos (as iniciais de revisores de exemplo), pintadas como no badge real.
    const states = wrapper.findAll('.approval__examples .pr-badge').map((b) => b.findAll('.faces__face').map((f) => f.attributes('data-state')))
    expect(states).toEqual([
      ['approved', 'pending'],
      ['approved', 'approved', 'pending'],
      ['approved', 'changes_requested', 'pending'],
    ])

    await wrapper.findAll('input[type="radio"]')[1].setValue()
    expect(statuses(wrapper)).toEqual(['aprovada', 'aprovada', 'ajustes_requisitados'])
  })

  it('salva a regra escolhida', async () => {
    const wrapper = mount(PrApprovalPanel)
    await flushPromises()
    const save = () => wrapper.findAll('.approval__footer button')[1]
    expect(save().attributes('disabled')).toBeDefined()

    await wrapper.findAll('input[type="radio"]')[1].setValue()
    await save().trigger('click')
    await flushPromises()

    expect(calls.at(-1)).toMatchObject({ method: 'PUT', body: { min_percent: 50 } })
    expect(calls.at(-1).url).toContain('/preferences/pr-approval')
    expect(wrapper.find('.approval__feedback').text()).toContain('Regra salva')
    expect(save().attributes('disabled')).toBeDefined()
  })
})
