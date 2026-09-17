import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import IssueNode from '@/components/sprint/IssueNode.vue'
import SprintView from '@/views/SprintView.vue'
import { routes } from '@/router/routes'
import { useScreenContextStore } from '@/stores/screenContext'
import { useSprintBoardStore } from '@/stores/sprintBoard'
import { useUiStore } from '@/stores/ui'
import {
  COLUMN_GAP,
  GROUP_HEADER,
  GROUP_PADDING,
  NODE_HEIGHT,
  NODE_WIDTH,
  implementationWaves,
  layoutGroup,
  layoutTree,
} from '@/utils/treeLayout'

function node(key, overrides = {}) {
  return {
    key,
    summary: `Resumo ${key}`,
    issue_type: 'Tarefa',
    status: 'Em Desenvolvimento',
    status_category: 'indeterminate',
    story_points: 3,
    assignee_name: 'Matheus Bacca',
    is_mine: true,
    in_sprint: true,
    is_parent_type: false,
    partial: false,
    parent_key: null,
    parent_via: null,
    group: '__sem_pai__',
    depth: 0,
    blocked: false,
    blocked_by: [],
    blocks: [],
    children: [],
    url: `https://weon.atlassian.net/browse/${key}`,
    pr: { status: 'sem_pr', status_label: 'Sem PR', pr_count: 0, open_pr_count: 0, build_failed: false },
    ...overrides,
  }
}

function sampleTree() {
  const children = ['WAI-2', 'WAI-3', 'WAI-4', 'WAI-5', 'WAI-6']
  return {
    sprint: { id: 3995, name: 'Sprint 73 - Growth', state: 'active', start_date: '2026-09-09T11:00:00Z', end_date: '2026-09-11T21:00:00Z', goal: null, issue_count: 7, mine_count: 7, done_count: 1 },
    only_mine: false,
    counters: { tasks: 7, parents: 1, blocked: 1, mine: 7, story_points: 21, done: 1 },
    nodes: [
      node('WAI-1', { issue_type: 'Épico', is_parent_type: true, in_sprint: false, group: 'WAI-1', children, pr: null }),
      ...children.map((k) => node(k, { parent_key: 'WAI-1', parent_via: 'parent', group: 'WAI-1', depth: 1 })),
      node('WAI-7', { children: ['WAI-8'] }),
      node('WAI-8', { issue_type: 'Subtarefa', parent_key: 'WAI-7', parent_via: 'parent', depth: 1, blocked: true, blocked_by: ['WAI-2'] }),
    ],
    edges: [
      ...children.map((k) => ({ source: 'WAI-1', target: k, kind: 'parent' })),
      { source: 'WAI-7', target: 'WAI-8', kind: 'parent' },
      { source: 'WAI-2', target: 'WAI-8', kind: 'blocks', label: 'bloqueia' },
    ],
    groups: [
      { key: 'WAI-1', root_key: 'WAI-1', issue_keys: ['WAI-1', ...children] },
      { key: '__sem_pai__', root_key: null, issue_keys: ['WAI-7', 'WAI-8'] },
    ],
  }
}

describe('layout da árvore', () => {
  it('raiz centralizada e todas as filhas lado a lado numa linha só', () => {
    const tree = sampleTree()
    const byKey = Object.fromEntries(tree.nodes.map((n) => [n.key, n]))

    const { positions, width, height } = layoutGroup(tree.groups[0], byKey)

    expect(width).toBe(5 * NODE_WIDTH + 4 * 20)
    expect(positions['WAI-1']).toEqual({ x: (width - NODE_WIDTH) / 2, y: 0 })
    const children = ['WAI-2', 'WAI-3', 'WAI-4', 'WAI-5', 'WAI-6']
    const rowY = positions['WAI-2'].y
    expect(children.map((k) => positions[k].y)).toEqual(children.map(() => rowY))
    expect(children.map((k) => positions[k].x)).toEqual([0, 1, 2, 3, 4].map((i) => i * (NODE_WIDTH + 20)))
    expect(height).toBe(rowY + NODE_HEIGHT)
  })

  it('épico com 14 filhas não quebra linha (caso real do QualificAI)', () => {
    const kids = Array.from({ length: 14 }, (_, i) => `WAI-${100 + i}`)
    const byKey = Object.fromEntries([
      ['WAI-99', node('WAI-99', { is_parent_type: true, in_sprint: false, children: kids })],
      ...kids.map((k) => [k, node(k, { parent_key: 'WAI-99' })]),
    ])

    const { positions, width } = layoutGroup({ key: 'WAI-99', root_key: 'WAI-99', issue_keys: ['WAI-99', ...kids] }, byKey)

    expect(new Set(kids.map((k) => positions[k].y)).size).toBe(1)
    expect(positions[kids.at(-1)].x).toBe(13 * (NODE_WIDTH + 20))
    expect(width).toBe(14 * NODE_WIDTH + 13 * 20)
  })

  it('grupo só com a raiz tem a altura de um card', () => {
    const byKey = { 'WAI-1': node('WAI-1', { is_parent_type: true, in_sprint: false }) }

    const { positions, width, height } = layoutGroup({ key: 'WAI-1', root_key: 'WAI-1', issue_keys: ['WAI-1'] }, byKey)

    expect(positions['WAI-1']).toEqual({ x: 0, y: 0 })
    expect([width, height]).toEqual([NODE_WIDTH, NODE_HEIGHT])
  })

  it('subtarefa fica empilhada abaixo da tarefa mãe no grupo "Sem pai"', () => {
    const tree = sampleTree()
    const byKey = Object.fromEntries(tree.nodes.map((n) => [n.key, n]))

    const { positions } = layoutGroup(tree.groups[1], byKey)

    expect(positions['WAI-8'].x).toBe(positions['WAI-7'].x)
    expect(positions['WAI-8'].y).toBeGreaterThan(positions['WAI-7'].y + NODE_HEIGHT)
  })

  it('gera molduras de grupo, nós e arestas por tipo', () => {
    const { nodes, edges } = layoutTree(sampleTree(), { selectedKey: 'WAI-3' })

    const frames = nodes.filter((n) => n.type === 'group-frame')
    expect(frames.map((f) => f.data.title)).toEqual([null, 'Sem pai'])
    expect(frames[0].data.count).toBe(5)

    const issue = nodes.find((n) => n.id === 'WAI-1')
    expect(issue.position).toEqual({
      x: frames[0].position.x + GROUP_PADDING + (5 * NODE_WIDTH + 80 - NODE_WIDTH) / 2,
      y: frames[0].position.y + GROUP_PADDING + GROUP_HEADER,
    })
    expect(nodes.find((n) => n.id === 'WAI-3').data.selected).toBe(true)

    const blocks = edges.find((e) => e.id === 'blocks:WAI-2->WAI-8')
    expect(blocks).toMatchObject({ label: 'bloqueia', animated: true, sourceHandle: 'right', targetHandle: 'left' })
    expect(edges.find((e) => e.id === 'parent:WAI-1->WAI-2')).toMatchObject({ type: 'smoothstep', sourceHandle: 'bottom' })
  })

  it('grupos que não cabem na linha descem para a próxima', () => {
    const tree = sampleTree()
    // 1º grupo: 5 filhas (1308px) · 2º: 3 filhas (804px) cabe ao lado · 3º ("Sem pai") estoura MAX_ROW_WIDTH
    const kids = ['WAI-91', 'WAI-92', 'WAI-93']
    tree.nodes.push(
      node('WAI-90', { is_parent_type: true, in_sprint: false, children: kids }),
      ...kids.map((k) => node(k, { parent_key: 'WAI-90' })),
    )
    tree.groups.splice(1, 0, { key: 'WAI-90', root_key: 'WAI-90', issue_keys: ['WAI-90', ...kids] })

    const frames = layoutTree(tree).nodes.filter((n) => n.type === 'group-frame')

    expect(frames[1].position.y).toBe(0)
    expect(frames[1].position.x).toBeGreaterThan(0)
    expect(frames[2].position.x).toBe(0)
    expect(frames[2].position.y).toBeGreaterThan(0)
  })

  it('grupo mais largo que a linha ocupa a linha sozinho', () => {
    const tree = sampleTree()
    const kids = Array.from({ length: 12 }, (_, i) => `WAI-${200 + i}`)
    tree.nodes.push(
      node('WAI-199', { is_parent_type: true, in_sprint: false, children: kids }),
      ...kids.map((k) => node(k, { parent_key: 'WAI-199' })),
    )
    tree.groups.splice(1, 0, { key: 'WAI-199', root_key: 'WAI-199', issue_keys: ['WAI-199', ...kids] })

    const frames = layoutTree(tree).nodes.filter((n) => n.type === 'group-frame')

    expect(frames.map((f) => f.position.x)).toEqual([0, 0, 0])
    expect(frames[1].position.y).toBeGreaterThan(frames[0].position.y)
    expect(frames[2].position.y).toBeGreaterThan(frames[1].position.y)
  })
})

describe('ondas de implementação', () => {
  // Recorte do épico WAI-7326 (QualificAI): duas correntes de bloqueio saindo da
  // mesma linha, uma delas com duas tarefas liberadas pelo mesmo bloqueador.
  function epicoComBloqueios() {
    const filhas = ['WAI-7889', 'WAI-8428', 'WAI-8429', 'WAI-8430', 'WAI-8432', 'WAI-8433', 'WAI-8434']
    const bloqueios = {
      'WAI-8429': ['WAI-8428'],
      'WAI-8430': ['WAI-8429'],
      'WAI-8433': ['WAI-8432'],
      'WAI-8434': ['WAI-8432'],
    }
    const nodes = [
      node('WAI-7326', { issue_type: 'Épico', is_parent_type: true, in_sprint: false, group: 'WAI-7326', children: filhas, pr: null }),
      ...filhas.map((k) =>
        node(k, {
          parent_key: 'WAI-7326',
          parent_via: 'parent',
          group: 'WAI-7326',
          depth: 1,
          blocked: Boolean(bloqueios[k]),
          blocked_by: bloqueios[k] ?? [],
          blocks: filhas.filter((outra) => (bloqueios[outra] ?? []).includes(k)),
        }),
      ),
    ]
    return {
      tree: {
        sprint: { id: 1, name: 'Sprint 73 - Growth', state: 'active', start_date: null, end_date: null, goal: null, issue_count: 7, mine_count: 7, done_count: 0 },
        only_mine: false,
        counters: {},
        nodes,
        edges: [
          ...filhas.map((k) => ({ source: 'WAI-7326', target: k, kind: 'parent' })),
          ...Object.entries(bloqueios).flatMap(([alvo, origens]) =>
            origens.map((origem) => ({ source: origem, target: alvo, kind: 'blocks', label: 'bloqueia' })),
          ),
        ],
        groups: [{ key: 'WAI-7326', root_key: 'WAI-7326', issue_keys: ['WAI-7326', ...filhas] }],
      },
      byKey: Object.fromEntries(nodes.map((n) => [n.key, n])),
    }
  }

  it('onda 1 é quem ninguém bloqueia; cada bloqueada entra uma onda depois', () => {
    const { tree, byKey } = epicoComBloqueios()

    const ondas = implementationWaves(tree.groups[0].issue_keys.filter((k) => k !== 'WAI-7326'), byKey)

    expect(ondas).toEqual([
      ['WAI-7889', 'WAI-8428', 'WAI-8432'],
      ['WAI-8429', 'WAI-8433', 'WAI-8434'],
      ['WAI-8430'],
    ])
  })

  it('bloqueador de outro grupo não empurra o card para outra onda', () => {
    const byKey = {
      'WAI-1': node('WAI-1', { blocked: true, blocked_by: ['WAI-999'] }),
      'WAI-2': node('WAI-2'),
    }

    expect(implementationWaves(['WAI-1', 'WAI-2'], byKey)).toEqual([['WAI-1', 'WAI-2']])
  })

  it('ciclo de bloqueio não trava o cálculo', () => {
    const byKey = {
      'WAI-1': node('WAI-1', { blocked: true, blocked_by: ['WAI-2'] }),
      'WAI-2': node('WAI-2', { blocked: true, blocked_by: ['WAI-1'] }),
    }

    const ondas = implementationWaves(['WAI-1', 'WAI-2'], byKey)

    expect(ondas.flat().sort()).toEqual(['WAI-1', 'WAI-2'])
  })

  it('a bloqueada cai na coluna do bloqueador, uma linha abaixo', () => {
    const { tree, byKey } = epicoComBloqueios()

    const { positions } = layoutGroup(tree.groups[0], byKey)

    expect(positions['WAI-8429'].x).toBe(positions['WAI-8428'].x)
    expect(positions['WAI-8429'].y).toBeGreaterThan(positions['WAI-8428'].y + NODE_HEIGHT)
    expect(positions['WAI-8430'].x).toBe(positions['WAI-8429'].x)
    expect(positions['WAI-8430'].y).toBeGreaterThan(positions['WAI-8429'].y + NODE_HEIGHT)
  })

  it('duas tarefas liberadas pela mesma ficam lado a lado na onda seguinte', () => {
    const { tree, byKey } = epicoComBloqueios()

    const { positions, width } = layoutGroup(tree.groups[0], byKey)

    expect(positions['WAI-8433'].x).toBe(positions['WAI-8432'].x)
    expect(positions['WAI-8434'].x).toBe(positions['WAI-8432'].x + NODE_WIDTH + COLUMN_GAP)
    expect(positions['WAI-8433'].y).toBe(positions['WAI-8434'].y)
    // A onda 2 alargou o grupo: a linha de cima tem 3 cards, a de baixo chega na 4ª coluna.
    expect(width).toBe(4 * NODE_WIDTH + 3 * COLUMN_GAP)
  })

  it('cada onda ganha uma faixa pontilhada numerada', () => {
    const { tree, byKey } = epicoComBloqueios()

    const { waves, positions } = layoutGroup(tree.groups[0], byKey)

    expect(waves.map((f) => f.index)).toEqual([1, 2, 3])
    expect(waves[0].y).toBeLessThan(positions['WAI-8428'].y)
    expect(waves[1].y).toBeGreaterThan(positions['WAI-8428'].y + NODE_HEIGHT)
    expect(waves[1].y).toBeLessThan(positions['WAI-8429'].y)
  })

  it('grupo sem bloqueio nenhum não ganha faixa', () => {
    const tree = sampleTree()
    const byKey = Object.fromEntries(tree.nodes.map((n) => [n.key, n]))

    expect(layoutGroup(tree.groups[0], byKey).waves).toEqual([])
    expect(layoutTree(tree).nodes.some((n) => n.type === 'wave-divider')).toBe(false)
  })

  it('a faixa vira nó do canvas, larga como o grupo e rotulada', () => {
    const { tree } = epicoComBloqueios()

    const faixas = layoutTree(tree).nodes.filter((n) => n.type === 'wave-divider')

    expect(faixas.map((f) => f.data.label)).toEqual([
      'Onda de implementação 1',
      'Onda de implementação 2',
      'Onda de implementação 3',
    ])
    expect(faixas[0].data.width).toBe(4 * NODE_WIDTH + 3 * COLUMN_GAP)
    expect(faixas.every((f) => f.selectable === false && f.draggable === false)).toBe(true)
  })

  it('bloqueio dentro do grupo vira seta de cima para baixo', () => {
    const { tree } = epicoComBloqueios()

    const { edges } = layoutTree(tree)

    expect(edges.find((e) => e.id === 'blocks:WAI-8428->WAI-8429')).toMatchObject({
      sourceHandle: 'bottom',
      targetHandle: 'top',
      type: 'smoothstep',
      label: 'bloqueia',
    })
  })

  it('o épico não puxa seta para quem já está pendurado num bloqueador', () => {
    const { tree } = epicoComBloqueios()

    const { edges } = layoutTree(tree)
    const doEpico = edges.filter((e) => e.source === 'WAI-7326').map((e) => e.target)

    expect(doEpico).toEqual(['WAI-7889', 'WAI-8428', 'WAI-8432'])
  })
})

describe('IssueNode', () => {
  const mountNode = (issue, selected = false) =>
    mount(IssueNode, { props: { data: { issue, selected } }, global: { stubs: { Handle: true } } })

  it('mostra tipo, título, chave, SP, status do Jira e badge do PR', () => {
    const wrapper = mountNode(node('WAI-7001', { pr: { status: 'ajustes_requisitados', pr_count: 2, open_pr_count: 1, build_failed: false } }))

    expect(wrapper.find('.node__type').text()).toBe('TAREFA')
    expect(wrapper.find('.node__title').text()).toBe('Resumo WAI-7001')
    expect(wrapper.find('.node__key').text()).toBe('WAI-7001')
    expect(wrapper.text()).toContain('3 SP')
    expect(wrapper.text()).toContain('Ajustes requisitados')
    expect(wrapper.text()).toContain('Em Desenvolvimento')
  })

  it('chave e SP ficam no cabeçalho, ao lado do tipo, e a chave abre o Jira', () => {
    const wrapper = mountNode(node('WAI-7001'))
    const header = wrapper.find('.node__header')
    const link = header.find('a.node__key')

    expect(header.text()).toContain('TAREFA')
    expect(header.text()).toContain('3 SP')
    expect(link.attributes('href')).toBe('https://weon.atlassian.net/browse/WAI-7001')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('rodapé sempre tem o ícone de lembretes, com a contagem quando há algum', () => {
    const vazio = mountNode(node('WAI-7001'))
    expect(vazio.find('.node__footer .node__notes').text()).toBe('')
    expect(vazio.find('.node__notes').classes()).not.toContain('node__notes--filled')

    const com = mountNode(node('WAI-7001', { note_count: 2 }))
    expect(com.find('.node__notes').text()).toBe('2')
    expect(com.find('.node__notes').attributes('title')).toBe('2 lembretes — abrir')
  })

  it('o ícone de lembretes pede a vista de lembretes e deixa o clique chegar ao canvas', async () => {
    setActivePinia(createPinia())
    const onClick = vi.fn()
    const wrapper = mount({ components: { IssueNode }, setup: () => ({ onClick, issue: node('WAI-7001') }), template: '<div @click="onClick"><IssueNode :data="{ issue, selected: false }" /></div>' }, { global: { stubs: { Handle: true } } })

    await wrapper.find('.node__notes').trigger('click')

    expect(onClick).toHaveBeenCalled()
    expect(useUiStore().consumeIssueTab('WAI-7001')).toBe('lembretes')
  })

  it('Alt + clique no ícone de lembretes não deixa pedido pendurado', async () => {
    setActivePinia(createPinia())
    const wrapper = mountNode(node('WAI-7001'))

    await wrapper.find('.node__notes').trigger('click', { altKey: true })

    expect(useUiStore().issueTabRequest).toBeNull()
  })

  it('clicar na chave não seleciona o card', async () => {
    const onClick = vi.fn()
    const wrapper = mount({ components: { IssueNode }, setup: () => ({ onClick, issue: node('WAI-7001') }), template: '<div @click="onClick"><IssueNode :data="{ issue, selected: false }" /></div>' }, { global: { stubs: { Handle: true } } })

    await wrapper.find('a.node__key').trigger('click')

    expect(onClick).not.toHaveBeenCalled()
  })

  it('link fora de http(s) não vira âncora', () => {
    const wrapper = mountNode(node('WAI-7001', { url: 'javascript:alert(1)' }))

    expect(wrapper.find('a.node__key').exists()).toBe(false)
    expect(wrapper.find('.node__key').text()).toBe('WAI-7001')
  })

  it('a cor do card acompanha a etapa do status, não o status do PR', () => {
    const review = { id: 'review', label: 'Review', color: '#f59e0b' }
    const wrapper = mountNode(node('WAI-7', { stage: review, pr: { status: 'aprovada', pr_count: 1, open_pr_count: 1, build_failed: false } }))

    expect(wrapper.attributes('style')).toContain('--tone: #f59e0b')
  })

  it('bloqueador sem PR aberta: ícone de bloqueio vermelho e diz por quem', () => {
    const wrapper = mountNode(node('WAI-8', { blocked: true, blocked_by: ['WAI-2'], blockers_without_pr: ['WAI-2'] }))

    expect(wrapper.find('.node__icon--blocked').exists()).toBe(true)
    expect(wrapper.find('.node__blocked').text()).toBe('bloqueada por WAI-2')
  })

  it('bloqueador com PR aberta: volta o ícone do tipo e some o "bloqueada por"', () => {
    const wrapper = mountNode(node('WAI-8', { blocked: true, blocked_by: ['WAI-2'], blockers_without_pr: [] }))

    expect(wrapper.find('.node__icon--blocked').exists()).toBe(false)
    expect(wrapper.find('.node__blocked').exists()).toBe(false)
  })

  it('com dois bloqueadores, o texto lista só o que ainda não abriu PR', () => {
    const wrapper = mountNode(node('WAI-8', { blocked: true, blocked_by: ['WAI-2', 'WAI-3'], blockers_without_pr: ['WAI-3'] }))

    expect(wrapper.find('.node__blocked').text()).toBe('bloqueada por WAI-3')
  })

  it('épico sem badge, com contagem de filhas; tarefa de outro dev mostra iniciais', () => {
    const epic = mountNode(node('WAI-1', { issue_type: 'Épico', is_parent_type: true, in_sprint: false, children: ['a', 'b'], pr: null }))
    expect(epic.find('.pr-badge').exists()).toBe(false)
    expect(epic.text()).toContain('2 filhas')

    const other = mountNode(node('WAI-9', { is_mine: false, assignee_name: 'Outro Dev' }))
    expect(other.find('.node__avatar').text()).toBe('OD')
  })

  it('status do Jira fica no contorno, na cor da etapa', () => {
    const wrapper = mountNode(node('WAI-7', { stage: { id: 'review', label: 'Review', color: '#f59e0b' }, status: 'DISPONIVEL PARA REVIEW' }))

    expect(wrapper.find('.node__status').text()).toBe('DISPONIVEL PARA REVIEW')
    expect(wrapper.find('.node__footer .node__status').exists()).toBe(false)
    expect(wrapper.attributes('style')).toContain('--tone: #f59e0b')
  })

  it('status sem etapa mapeada cai na cor de borda neutra', () => {
    expect(mountNode(node('WAI-7', { stage: null })).attributes('style')).toContain('--tone: var(--color-border-strong)')
  })

  describe('sombra pulsante', () => {
    const DEV = { id: 'desenvolvimento', label: 'Desenvolvimento', color: '#2f7cf6' }
    const REVIEW = { id: 'review', label: 'Review', color: '#f59e0b' }
    const changes = { status: 'ajustes_requisitados', pr_count: 1, open_pr_count: 1, build_failed: false }

    it('tarefa em desenvolvimento pulsa na cor da etapa', () => {
      const wrapper = mountNode(node('WAI-7', { stage: DEV }))

      expect(wrapper.classes()).toContain('node--pulse')
      expect(wrapper.attributes('data-pulse')).toBe('desenvolvimento')
      expect(wrapper.attributes('style')).toContain('--pulse: var(--tone)')
    })

    it('PR com ajustes requisitados pulsa na cor do status, mesmo fora de desenvolvimento', () => {
      const wrapper = mountNode(node('WAI-7', { stage: REVIEW, pr: changes }))

      expect(wrapper.attributes('data-pulse')).toBe('ajustes')
      expect(wrapper.attributes('style')).toContain('--pulse: var(--pr-changes)')
    })

    it('ajustes requisitados ganha de desenvolvimento', () => {
      expect(mountNode(node('WAI-7', { stage: DEV, pr: changes })).attributes('data-pulse')).toBe('ajustes')
    })

    it('outras etapas, pai e card fora da sprint não pulsam', () => {
      expect(mountNode(node('WAI-7', { stage: REVIEW })).classes()).not.toContain('node--pulse')
      expect(mountNode(node('WAI-1', { stage: DEV, is_parent_type: true, pr: null })).classes()).not.toContain('node--pulse')
      expect(mountNode(node('WAI-7', { stage: DEV, in_sprint: false, pr: changes })).classes()).not.toContain('node--pulse')
    })
  })

  it('card atualizado desde a última visita mostra a bolinha e conta o que mudou', () => {
    const wrapper = mountNode(node('WAI-7', { unseen_changes: ['status', 'pr'] }))

    expect(wrapper.find('.node__updated').attributes('title')).toBe('Atualizada desde a última visita: status, etapa do PR')
    expect(mountNode(node('WAI-7', { unseen_changes: [] })).find('.node__updated').exists()).toBe(false)
  })
})

describe('SprintView', () => {
  const SPRINTS = [
    { id: 3995, name: 'Sprint 73 - Growth', state: 'active', issue_count: 7, mine_count: 7, done_count: 1 },
    { id: 3997, name: 'Sprint 74 - Growth', state: 'future', issue_count: 1, mine_count: 1, done_count: 0 },
    { id: 3961, name: 'Sprint 72 - Growth', state: 'closed', issue_count: 26, mine_count: 26, done_count: 26 },
  ]

  function json(body) {
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }
  }

  let calls
  beforeEach(() => {
    setActivePinia(createPinia())
    calls = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        calls.push(url)
        if (url === '/api/sprints') return json(SPRINTS)
        if (url.startsWith('/api/sprints/')) return json(sampleTree())
        if (url === '/api/sync/scope') return json({ jira: { assignee_scope: 'mine' }, bitbucket: {} })
        throw new Error(`não mockado: ${url}`)
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  async function mountView(query = '') {
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push(`/sprints${query}`)
    await router.isReady()
    const wrapper = mount(SprintView, {
      global: {
        plugins: [router],
        stubs: { SprintCanvas: { name: 'SprintCanvas', props: ['tree', 'selectedKey', 'matchKeys', 'focusKey', 'highlightStatus'], emits: ['select', 'highlight'], template: '<div class="canvas-stub" />' } },
      },
    })
    await flushPromises()
    return { wrapper, router }
  }

  it('abre a sprint ativa por padrão com contadores e seletor agrupado', async () => {
    const { wrapper } = await mountView()

    expect(calls).toContain('/api/sprints/3995/tree')
    expect(wrapper.findAll('optgroup').map((g) => g.attributes('label'))).toEqual(['Ativas', 'Futuras', 'Fechadas'])
    // Período, concluídas e SP dentro do componente da sprint; tarefas e bloqueios saíram.
    const summary = wrapper.find('.sprint__nav .sprint__summary').text()
    expect(summary).toContain('1/7 concluídas')
    expect(summary).toContain('21 SP')
    expect(wrapper.text()).not.toContain('7 tarefas')
    expect(wrapper.text()).not.toContain('bloqueio(s)')
    // Resumo da sprint flutua sobre o canvas, que ocupa a tela toda.
    expect(wrapper.find('.sprint__overlay .sprint__panel').exists()).toBe(true)
    expect(wrapper.find('.sprint__canvas .canvas-stub').exists()).toBe(true)
    expect(wrapper.find('.sprint__nav').attributes('data-state')).toBe('active')
    expect(wrapper.find('.canvas-stub').exists()).toBe(true)
    // com escopo "só as minhas" o filtro não aparece
    expect(wrapper.find('.sprint__mine').exists()).toBe(false)
  })

  it('troca de sprint pela URL e publica o contexto de tela', async () => {
    const { wrapper, router } = await mountView('?sprint=3961')

    expect(calls).toContain('/api/sprints/3961/tree')
    const screen = useScreenContextStore()
    expect(screen.view).toBe('sprint')
    expect(screen.sprintId).toBe(3961)
    expect(screen.visibleIssueKeys).toContain('WAI-2')
    expect(screen.visibleIssueKeys).not.toContain('WAI-1') // épico fora da sprint

    wrapper.findComponent({ name: 'SprintCanvas' }).vm.$emit('select', 'WAI-3')
    await flushPromises()
    expect(router.currentRoute.value.query.tarefa).toBe('WAI-3')
    expect(screen.focusedIssueKey).toBe('WAI-3')
  })

  it('abrir um card atualizado apaga a bolinha e avisa o back', async () => {
    const posts = []
    const tree = sampleTree()
    tree.nodes.find((n) => n.key === 'WAI-3').unseen_changes = ['status']
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (options.method === 'POST') {
          posts.push(url)
          return { ok: true, status: 204, headers: new Headers(), text: async () => '' }
        }
        if (url === '/api/sprints') return json(SPRINTS)
        if (url.startsWith('/api/sprints/')) return json(tree)
        if (url === '/api/sync/scope') return json({ jira: { assignee_scope: 'mine' }, bitbucket: {} })
        throw new Error(`não mockado: ${url}`)
      }),
    )
    const { wrapper } = await mountView()
    const board = useSprintBoardStore()
    expect(posts).toEqual([])

    wrapper.findComponent({ name: 'SprintCanvas' }).vm.$emit('select', 'WAI-3')
    await flushPromises()

    expect(posts).toEqual(['/api/issues/WAI-3/seen'])
    expect(board.tree.nodes.find((n) => n.key === 'WAI-3').unseen_changes).toEqual([])

    // Card já visto não chama o back de novo.
    wrapper.findComponent({ name: 'SprintCanvas' }).vm.$emit('select', 'WAI-2')
    await flushPromises()
    expect(posts).toEqual(['/api/issues/WAI-3/seen'])
  })

  it('só a última árvore pedida é aplicada (troca rápida de sprint)', async () => {
    let release
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        if (url === '/api/sprints/1/tree') {
          await new Promise((r) => (release = r))
          return json({ ...sampleTree(), sprint: { ...sampleTree().sprint, name: 'antiga' } })
        }
        return json({ ...sampleTree(), sprint: { ...sampleTree().sprint, name: 'nova' } })
      }),
    )
    const board = useSprintBoardStore()

    const slow = board.loadTree(1)
    await board.loadTree(2)
    release()
    await slow

    expect(board.tree.sprint.name).toBe('nova')
  })
})

describe('SprintView: setas entre sprints', () => {
  const SPRINTS = [
    { id: 3997, name: 'Sprint 74 - Growth', state: 'future', start_date: '2026-09-14T11:00:00Z', issue_count: 1, mine_count: 1, done_count: 0 },
    { id: 3995, name: 'Sprint 73 - Growth', state: 'active', start_date: '2026-09-09T11:00:00Z', issue_count: 7, mine_count: 7, done_count: 1 },
    { id: 3961, name: 'Sprint 72 - Growth', state: 'closed', start_date: '2026-09-01T11:00:00Z', issue_count: 26, mine_count: 26, done_count: 26 },
  ]

  function json(body) {
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        if (url === '/api/sprints') return json(SPRINTS)
        if (url.startsWith('/api/sprints/')) {
          const id = Number(url.split('/')[3])
          return json({ ...sampleTree(), sprint: SPRINTS.find((s) => s.id === id) })
        }
        if (url === '/api/sync/scope') return json({ jira: { assignee_scope: 'mine' }, bitbucket: {} })
        throw new Error(`não mockado: ${url}`)
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  async function mountView(query = '') {
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push(`/sprints${query}`)
    await router.isReady()
    const wrapper = mount(SprintView, {
      global: {
        plugins: [router],
        stubs: { SprintCanvas: { name: 'SprintCanvas', props: ['tree', 'selectedKey', 'matchKeys', 'focusKey', 'highlightStatus'], emits: ['select', 'highlight'], template: '<div class="canvas-stub" />' } },
      },
    })
    await flushPromises()
    return { wrapper, router }
  }

  it('anterior e próxima seguem a data de início; a ativa fica verde, as outras roxas', async () => {
    const { wrapper, router } = await mountView()
    const prev = () => wrapper.find('[aria-label="Sprint anterior"]')
    const next = () => wrapper.find('[aria-label="Próxima sprint"]')
    expect(wrapper.find('.sprint__nav').attributes('data-state')).toBe('active')

    await next().trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.sprint).toBe('3997')
    expect(wrapper.find('.sprint__nav').attributes('data-state')).toBe('future')
    expect(next().attributes('disabled')).toBeDefined()

    await prev().trigger('click')
    await flushPromises()
    await prev().trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.sprint).toBe('3961')
    expect(wrapper.find('.sprint__nav').attributes('data-state')).toBe('closed')
    expect(prev().attributes('disabled')).toBeDefined()
  })

  it('trocar de sprint fecha a tarefa aberta', async () => {
    const { wrapper, router } = await mountView('?sprint=3995&tarefa=WAI-3')

    await wrapper.find('[aria-label="Sprint anterior"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toMatchObject({ sprint: '3961' })
    expect(router.currentRoute.value.query.tarefa).toBeUndefined()
  })
})

describe('busca no canvas e destaque de status', () => {
  const SPRINTS = [{ id: 3995, name: 'Sprint 73 - Growth', state: 'active', issue_count: 7, mine_count: 7, done_count: 1 }]

  function json(body) {
    return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        if (url === '/api/sprints') return json(SPRINTS)
        if (url.startsWith('/api/sprints/')) return json(sampleTree())
        if (url === '/api/sync/scope') return json({ jira: { assignee_scope: 'mine' }, bitbucket: {} })
        throw new Error(`não mockado: ${url}`)
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  async function mountView(options = {}) {
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/sprints')
    await router.isReady()
    const wrapper = mount(SprintView, {
      ...options,
      global: {
        plugins: [router],
        stubs: { SprintCanvas: { name: 'SprintCanvas', props: ['tree', 'selectedKey', 'matchKeys', 'focusKey', 'highlightStatus'], emits: ['select', 'highlight'], template: '<div class="canvas-stub" />' } },
      },
    })
    await flushPromises()
    return wrapper
  }

  const canvas = (wrapper) => wrapper.findComponent({ name: 'SprintCanvas' })

  function ctrlF() {
    const event = new KeyboardEvent('keydown', { key: 'f', ctrlKey: true, cancelable: true })
    window.dispatchEvent(event)
    return event
  }

  async function search(wrapper, text) {
    if (!wrapper.find('.find__input').exists()) {
      ctrlF()
      await flushPromises()
    }
    const input = wrapper.find('.find__input')
    await input.setValue(text)
    await flushPromises()
    return input
  }

  it('sem busca, nenhum card marcado e a câmera livre', async () => {
    const wrapper = await mountView()

    expect(canvas(wrapper).props('matchKeys')).toEqual([])
    expect(canvas(wrapper).props('focusKey')).toBeNull()
  })

  it('acha por título sem acento nem caixa e foca o primeiro', async () => {
    const wrapper = await mountView()

    await search(wrapper, 'RESUMO wai-2')

    expect(canvas(wrapper).props('matchKeys')).toEqual(['WAI-2'])
    expect(canvas(wrapper).props('focusKey')).toBe('WAI-2')
    expect(wrapper.find('.find__count').text()).toBe('1/1')
  })

  it('anda pelos resultados e dá a volta no fim da lista', async () => {
    const wrapper = await mountView()
    await search(wrapper, 'resumo')
    const total = canvas(wrapper).props('matchKeys').length
    expect(total).toBeGreaterThan(2)

    const primeiro = canvas(wrapper).props('focusKey')
    await wrapper.find('[aria-label="Próximo resultado"]').trigger('click')
    const segundo = canvas(wrapper).props('focusKey')
    expect(segundo).not.toBe(primeiro)
    expect(wrapper.find('.find__count').text()).toBe(`2/${total}`)

    await wrapper.find('[aria-label="Resultado anterior"]').trigger('click')
    expect(canvas(wrapper).props('focusKey')).toBe(primeiro)

    // Uma volta inteira para trás cai no último.
    await wrapper.find('[aria-label="Resultado anterior"]').trigger('click')
    expect(wrapper.find('.find__count').text()).toBe(`${total}/${total}`)
  })

  it('termo de uma letra só não busca', async () => {
    const wrapper = await mountView()

    await search(wrapper, 'w')

    expect(canvas(wrapper).props('matchKeys')).toEqual([])
    expect(wrapper.find('.find__count').text()).toBe('nada')
  })

  it('a busca só aparece no Ctrl+F, que não chega à busca do navegador', async () => {
    const wrapper = await mountView({ attachTo: document.body })
    expect(wrapper.find('.find__input').exists()).toBe(false)
    expect(wrapper.find('.sprint__panel .find').exists()).toBe(false)

    const event = ctrlF()
    await flushPromises()

    expect(event.defaultPrevented).toBe(true)
    expect(wrapper.find('.sprint__find .find__input').exists()).toBe(true)
    expect(document.activeElement).toBe(wrapper.find('.find__input').element)
    wrapper.unmount()
  })

  it('Ctrl+F com um diálogo aberto fica com o navegador', async () => {
    const wrapper = await mountView()
    const dialog = document.createElement('div')
    dialog.setAttribute('aria-modal', 'true')
    document.body.appendChild(dialog)

    const event = ctrlF()
    await flushPromises()

    expect(event.defaultPrevented).toBe(false)
    expect(wrapper.find('.find__input').exists()).toBe(false)
    dialog.remove()
  })

  it('fechar some com a caixa, zera a busca e solta a câmera', async () => {
    const wrapper = await mountView()
    await search(wrapper, 'resumo')

    await wrapper.find('[aria-label="Fechar busca"]').trigger('click')
    await flushPromises()

    expect(canvas(wrapper).props('focusKey')).toBeNull()
    expect(canvas(wrapper).props('matchKeys')).toEqual([])
    expect(wrapper.find('.find__input').exists()).toBe(false)
  })

  it('Alt + clique num card liga o destaque; o mesmo status de novo desliga; o X limpa', async () => {
    const wrapper = await mountView()
    expect(canvas(wrapper).props('highlightStatus')).toBeNull()

    canvas(wrapper).vm.$emit('highlight', 'Em Desenvolvimento')
    await flushPromises()
    expect(canvas(wrapper).props('highlightStatus')).toBe('Em Desenvolvimento')
    expect(wrapper.find('.sprint__highlight').text()).toContain('Em Desenvolvimento')

    canvas(wrapper).vm.$emit('highlight', 'Em Desenvolvimento')
    await flushPromises()
    expect(canvas(wrapper).props('highlightStatus')).toBeNull()

    canvas(wrapper).vm.$emit('highlight', 'Concluído')
    await flushPromises()
    await wrapper.find('[aria-label="Limpar destaque"]').trigger('click')
    expect(canvas(wrapper).props('highlightStatus')).toBeNull()
  })
})
