import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import JiraActionPopover from '@/components/jira/JiraActionPopover.vue'
import StatusChip from '@/components/jira/StatusChip.vue'
import StoryPointsChip from '@/components/jira/StoryPointsChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import SprintCanvas from '@/components/sprint/SprintCanvas.vue'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { useRefreshStore } from '@/stores/refresh'

const KEY = 'WAI-8434'

function step(status, extra = {}) {
  return {
    status,
    category: 'indeterminate',
    stage: { id: 'x', label: 'Etapa', color: 'var(--pr-open)' },
    current: false,
    transition_id: null,
    transition_name: null,
    requires_fields: false,
    ...extra,
  }
}

const FLOW = {
  issue_key: KEY,
  url: `https://weon.atlassian.net/browse/${KEY}`,
  status: 'Em Review',
  mirror_status: null,
  steps: [
    step('Em Desenvolvimento', { transition_id: '11', transition_name: 'Voltar' }),
    step('Em Review', { current: true }),
    step('DISPONIVEL PARA TESTES', { transition_id: '31', transition_name: 'Aprovar' }),
    step('Concluído', { transition_id: '41', requires_fields: true, transition_name: 'Fechar' }),
    step('Cancelado'),
  ],
}

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }
}

function written(extra = {}) {
  return json(200, {
    issue_key: KEY,
    status: 'DISPONIVEL PARA TESTES',
    status_category: 'new',
    story_points: 3,
    stage: null,
    write_id: 'w-1',
    ...extra,
  })
}

let fetchMock

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn(async (url) => (String(url).endsWith('/transitions') ? json(200, FLOW) : json(404, {})))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

function calls(method) {
  return fetchMock.mock.calls.filter(([, init]) => (init?.method ?? 'GET') === method)
}

/** Monta o popover global e o chip que o abre, os dois no body como no app. */
async function openStatus() {
  const popover = mount(JiraActionPopover, { attachTo: document.body })
  const chip = mount(StatusChip, { props: { issueKey: KEY, status: 'Em Review' }, attachTo: document.body })
  await chip.trigger('click')
  await flushPromises()
  return { popover, chip }
}

function stepEl(status) {
  return document.querySelector(`.flow__step[data-status="${status}"]`)
}

// --- Status ----------------------------------------------------------------------------

describe('linha de fluxo do status', () => {
  it('abre pelo selo e mostra o workflow na ordem, com o atual marcado', async () => {
    const { popover } = await openStatus()

    expect(fetchMock.mock.calls[0][0]).toBe(`/api/issues/${KEY}/transitions`)
    const names = [...document.querySelectorAll('.flow__step')].map((el) => el.dataset.status)
    expect(names).toEqual(FLOW.steps.map((s) => s.status))
    expect(stepEl('Em Review').classList.contains('flow__step--current')).toBe(true)
    // Atual, sem transição e com campo obrigatório não são botões: não dá para escolher.
    expect(stepEl('Em Review').querySelector('button')).toBeNull()
    expect(stepEl('Cancelado').querySelector('button')).toBeNull()
    expect(stepEl('Concluído').querySelector('button')).toBeNull()
    expect(stepEl('Concluído').textContent).toContain('pede campos no Jira')
    popover.unmount()
  })

  it('clique só escolhe; o duplo clique é que move no Jira', async () => {
    fetchMock.mockImplementation(async (url, init) => {
      if (init?.method === 'POST') return written()
      return json(200, FLOW)
    })
    const { popover } = await openStatus()
    const button = stepEl('DISPONIVEL PARA TESTES').querySelector('button')

    button.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }))
    await flushPromises()
    expect(calls('POST')).toHaveLength(0)
    expect(stepEl('DISPONIVEL PARA TESTES').classList.contains('flow__step--selected')).toBe(true)
    expect(document.querySelector('.flow__hint').textContent).toContain('Duplo clique em DISPONIVEL PARA TESTES')

    button.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))
    await flushPromises()

    const [url, init] = calls('POST')[0]
    expect(url).toBe(`/api/issues/${KEY}/transitions`)
    expect(JSON.parse(init.body)).toEqual({ transition_id: '31' })
    const store = useJiraActionsStore()
    expect(store.open).toBeNull()
    expect(store.lastWrite).toMatchObject({ id: 'w-1', key: KEY })
    popover.unmount()
  })

  it('pelo teclado, o segundo Enter no passo escolhido confirma', async () => {
    fetchMock.mockImplementation(async (url, init) => (init?.method === 'POST' ? written() : json(200, FLOW)))
    const { popover } = await openStatus()
    const button = stepEl('Em Desenvolvimento').querySelector('button')

    // Enter num botão vira clique com `detail` 0.
    button.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))
    await flushPromises()
    expect(calls('POST')).toHaveLength(0)

    button.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 0 }))
    await flushPromises()
    expect(JSON.parse(calls('POST')[0][1].body)).toEqual({ transition_id: '11' })
    popover.unmount()
  })

  it('erro do Jira fica no painel, que continua aberto', async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === 'POST' ? json(502, { detail: 'Jira: sem permissão para mover WAI-8434' }) : json(200, FLOW),
    )
    const { popover } = await openStatus()

    stepEl('DISPONIVEL PARA TESTES').querySelector('button').dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))
    await flushPromises()

    expect(useJiraActionsStore().open).not.toBeNull()
    expect(document.querySelector('.jira-popover [role="alert"]').textContent).toContain('sem permissão')
    popover.unmount()
  })

  it('status sem etapa ficam recolhidos em "Outros status"', async () => {
    const loose = { stage: null, category: 'new' }
    fetchMock.mockImplementation(async () =>
      json(200, {
        ...FLOW,
        steps: [
          step('Cruzeiro', { ...loose, transition_id: '5' }),
          ...FLOW.steps,
          step('IMPLANTAÇÃO', { ...loose, transition_id: '6' }),
        ],
      }),
    )
    const { popover } = await openStatus()
    const visible = () => [...document.querySelectorAll('.flow__step')].map((el) => el.dataset.status)

    expect(visible()).not.toContain('Cruzeiro')
    const toggle = document.querySelector('.flow__toggle')
    expect(toggle.textContent).toContain('Outros status (2)')

    toggle.click()
    await flushPromises()
    expect(visible().slice(-2)).toEqual(['Cruzeiro', 'IMPLANTAÇÃO'])
    popover.unmount()
  })

  it('avisa quando o Jira já está noutro status que o espelho', async () => {
    fetchMock.mockImplementation(async () => json(200, { ...FLOW, mirror_status: 'Em Desenvolvimento' }))
    const { popover } = await openStatus()

    expect(document.querySelector('.flow__note').textContent).toContain('a tela mostrava Em Desenvolvimento')
    popover.unmount()
  })

  it('Esc fecha só o painel, sem chegar a quem está por baixo', async () => {
    const underneath = vi.fn()
    window.addEventListener('keydown', underneath)
    const { popover } = await openStatus()

    // Do body, como a tecla chega de verdade: passa pela captura da janela antes de tudo.
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(useJiraActionsStore().open).toBeNull()
    expect(underneath).not.toHaveBeenCalled()
    window.removeEventListener('keydown', underneath)
    popover.unmount()
  })

  it('clique fora fecha; clicar de novo no selo também', async () => {
    const { popover, chip } = await openStatus()
    const store = useJiraActionsStore()

    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(store.open).toBeNull()

    await chip.trigger('click')
    expect(store.open?.kind).toBe('status')
    await chip.trigger('click')
    expect(store.open).toBeNull()
    popover.unmount()
  })

  it('o clique no selo não chega ao card', async () => {
    const onCard = vi.fn()
    const wrapper = mount(
      { components: { StatusChip }, template: `<div @click="onCard"><StatusChip issue-key="${KEY}" status="Em Review" /></div>`, methods: { onCard } },
      { attachTo: document.body },
    )

    await wrapper.find('button').trigger('click')
    expect(onCard).not.toHaveBeenCalled()

    // Alt + clique é o destaque de status do canvas: passa direto, sem abrir o painel.
    useJiraActionsStore().close()
    await wrapper.find('button').trigger('click', { altKey: true })
    expect(onCard).toHaveBeenCalledTimes(1)
    expect(useJiraActionsStore().open).toBeNull()
    wrapper.unmount()
  })
})

// --- Story Points ----------------------------------------------------------------------

describe('editor de Story Points', () => {
  async function openPoints(points = 3) {
    fetchMock.mockImplementation(async (url, init) => (init?.method === 'PUT' ? written({ story_points: 5 }) : json(404, {})))
    const popover = mount(JiraActionPopover, { attachTo: document.body })
    const chip = mount(StoryPointsChip, { props: { issueKey: KEY, points }, attachTo: document.body })
    await chip.trigger('click')
    await flushPromises()
    return { popover, chip, input: document.querySelector('.points__input') }
  }

  function puts() {
    return calls('PUT').map(([url, init]) => [url, JSON.parse(init.body)])
  }

  it('o chip mostra o valor e, sem valor, o convite a preencher', () => {
    expect(mount(StoryPointsChip, { props: { issueKey: KEY, points: 5 } }).text()).toBe('5 SP')
    expect(mount(StoryPointsChip, { props: { issueKey: KEY, points: 5, suffix: false } }).text()).toBe('5')
    const empty = mount(StoryPointsChip, { props: { issueKey: KEY, points: null } })
    expect(empty.text()).toBe('sem SP')
    expect(empty.attributes('data-empty')).toBeDefined()
  })

  it('clique num atalho preenche; duplo clique grava', async () => {
    const { popover, input } = await openPoints()
    const five = [...document.querySelectorAll('.points__pick')].find((b) => b.textContent.trim() === '5')

    five.click()
    await flushPromises()
    expect(input.value).toBe('5')
    expect(puts()).toEqual([])

    five.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))
    await flushPromises()
    expect(puts()).toEqual([[`/api/issues/${KEY}/story-points`, { story_points: 5 }]])
    expect(useJiraActionsStore().open).toBeNull()
    popover.unmount()
  })

  it('Enter grava o valor digitado, com vírgula', async () => {
    const { popover, input } = await openPoints()

    input.value = '0,5'
    input.dispatchEvent(new Event('input'))
    document.querySelector('.points').dispatchEvent(new Event('submit', { cancelable: true }))
    await flushPromises()

    expect(puts()).toEqual([[`/api/issues/${KEY}/story-points`, { story_points: 0.5 }]])
    popover.unmount()
  })

  it('campo vazio não apaga e inválido avisa; tirar os pontos é o Remover', async () => {
    const { popover, input } = await openPoints()
    const submit = document.querySelector('.points button[type="submit"]')

    input.value = ''
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    expect(submit.disabled).toBe(true)

    input.value = '-2'
    input.dispatchEvent(new Event('input'))
    await flushPromises()
    expect(submit.disabled).toBe(true)
    expect(document.querySelector('.points__error').textContent).toContain('0 a 999')

    document.querySelector('.points__remove').click()
    await flushPromises()
    expect(puts()).toEqual([[`/api/issues/${KEY}/story-points`, { story_points: null }]])
    popover.unmount()
  })

  it('mesmo valor fecha sem escrever no Jira', async () => {
    const { popover } = await openPoints(3)

    document.querySelector('.points').dispatchEvent(new Event('submit', { cancelable: true }))
    await flushPromises()

    expect(puts()).toEqual([])
    expect(useJiraActionsStore().open).toBeNull()
    popover.unmount()
  })
})

// --- Badge de PR -----------------------------------------------------------------------

describe('badge de PR leva ao Bitbucket', () => {
  const link = (id, repo = 'monitoria') => ({
    repo_slug: repo,
    id,
    title: `PR ${id}`,
    status: 'pr_aberta',
    status_label: 'PR aberta',
    url: `https://bitbucket.org/weonrepo/${repo}/pull-requests/${id}`,
  })

  it('um PR: o badge é o link', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'mergeada', prCount: 1, links: [link(412)] } })

    expect(wrapper.element.tagName).toBe('A')
    expect(wrapper.attributes('href')).toBe('https://bitbucket.org/weonrepo/monitoria/pull-requests/412')
    expect(wrapper.attributes('target')).toBe('_blank')
    expect(wrapper.attributes('rel')).toBe('noopener noreferrer')
    expect(wrapper.attributes('title')).toBe('Mergeada — abrir no Bitbucket')
  })

  it('link que não é http não vira href', () => {
    const wrapper = mount(PrStatusBadge, {
      props: { status: 'pr_aberta', links: [{ ...link(1), url: 'javascript:alert(1)' }] },
    })

    expect(wrapper.element.tagName).toBe('SPAN')
  })

  it('sem PR continua só rótulo', () => {
    const wrapper = mount(PrStatusBadge, { props: { status: 'branch_sem_pr' } })

    expect(wrapper.element.tagName).toBe('SPAN')
  })

  it('vários PRs: abre a lista para escolher, e o clique não abre o card', async () => {
    const onCard = vi.fn()
    const popover = mount(JiraActionPopover, { attachTo: document.body })
    const wrapper = mount(
      {
        components: { PrStatusBadge },
        data: () => ({ links: [link(10, 'supervisor-web'), link(20, 'weaction-api')] }),
        template: `<div @click="onCard"><PrStatusBadge status="ajustes_requisitados" :pr-count="2" :links="links" issue-key="${KEY}" /></div>`,
        methods: { onCard },
      },
      { attachTo: document.body },
    )

    await wrapper.find('button.pr-badge').trigger('click')
    await flushPromises()

    expect(onCard).not.toHaveBeenCalled()
    const items = [...document.querySelectorAll('.prlinks__item')]
    expect(items.map((a) => a.getAttribute('href'))).toEqual([
      'https://bitbucket.org/weonrepo/supervisor-web/pull-requests/10',
      'https://bitbucket.org/weonrepo/weaction-api/pull-requests/20',
    ])
    expect(document.querySelector('.prlinks__title').textContent).toBe(`2 PRs de ${KEY}`)
    wrapper.unmount()
    popover.unmount()
  })

  it('a aba PRs aponta o badge de cada PR para ele mesmo', () => {
    const wrapper = mount(PrStatusBadge, {
      props: { status: 'aprovada', href: 'https://bitbucket.org/weonrepo/monitoria/pull-requests/7', links: [link(1), link(2)] },
    })

    expect(wrapper.attributes('href')).toBe('https://bitbucket.org/weonrepo/monitoria/pull-requests/7')
  })
})

// --- Recarga depois da escrita ---------------------------------------------------------

describe('recarga depois de escrever no Jira', () => {
  it('a mesma escrita pelos dois caminhos recarrega uma vez só', () => {
    const refresh = useRefreshStore()

    refresh.afterWrite('w-1') // resposta do POST
    refresh.afterWrite('w-1') // `issue.changed` pelo stream
    expect(refresh.revision).toBe(1)
    expect(refresh.reason).toBe('jira')

    refresh.afterWrite('w-2')
    expect(refresh.revision).toBe(2)
  })

  it('recarregar a mesma sprint não tira a câmera do lugar', async () => {
    vi.useFakeTimers()
    const fitView = vi.fn()
    const nodes = [{ key: 'WAI-1' }, { key: 'WAI-2' }]
    const tree = { sprint: { id: 3995 }, nodes, edges: [], groups: [] }
    const VueFlowStub = { name: 'VueFlow', emits: ['pane-ready', 'node-click', 'pane-click'], template: '<div />' }
    const wrapper = mount(SprintCanvas, {
      props: { tree },
      global: { stubs: { VueFlow: VueFlowStub, Background: true, Controls: true } },
    })
    wrapper.findComponent(VueFlowStub).vm.$emit('pane-ready', { fitView })

    // Status mudou num card: árvore nova, mesmos cards.
    await wrapper.setProps({ tree: { ...tree, nodes: nodes.map((n) => ({ ...n, status: 'Em Review' })) } })
    await vi.runAllTimersAsync()
    expect(fitView).not.toHaveBeenCalled()

    // Outra sprint: aí reenquadra.
    await wrapper.setProps({ tree: { ...tree, sprint: { id: 3996 } } })
    await vi.runAllTimersAsync()
    expect(fitView).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })
})
