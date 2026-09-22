import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import IssueNode from '@/components/sprint/IssueNode.vue'
import SprintCanvas from '@/components/sprint/SprintCanvas.vue'
import SprintSearch from '@/components/sprint/SprintSearch.vue'
import { nodeMarks } from '@/components/sprint/canvasMarks'

function issue(key, { status = 'sem_pr', inSprint = true, parent = false } = {}) {
  return {
    key,
    summary: `Resumo ${key}`,
    issue_type: parent ? 'Épico' : 'Tarefa',
    status: 'Em Desenvolvimento',
    status_category: 'indeterminate',
    story_points: 3,
    assignee_name: 'Matheus Bacca',
    is_mine: true,
    in_sprint: inSprint,
    is_parent_type: parent,
    partial: false,
    parent_via: null,
    blocked: false,
    blocked_by: [],
    children: [],
    pr: status ? { status, status_label: status, pr_count: 1, build_failed: false } : null,
  }
}

// --- marcação dos cards (busca + destaque de status) ------------------------------------------

describe('nodeMarks', () => {
  const aprovada = issue('WAI-2', { status: 'aprovada' })
  const ajustes = { ...issue('WAI-3', { status: 'ajustes_requisitados' }), status: 'DISPONIVEL PARA REVIEW' }
  const epico = issue('WAI-1', { status: null, inSprint: false, parent: true })

  it('sem busca e sem destaque, nenhum card fica marcado', () => {
    expect(nodeMarks(aprovada)).toEqual({ match: false, active: false, emphasized: false, muted: false })
  })

  it('resultado da busca fica marcado e o da vez fica ativo', () => {
    const marks = { matchKeys: ['WAI-2', 'WAI-3'], focusKey: 'WAI-3' }

    expect(nodeMarks(aprovada, marks)).toMatchObject({ match: true, active: false })
    expect(nodeMarks(ajustes, marks)).toMatchObject({ match: true, active: true })
    expect(nodeMarks(epico, marks).match).toBe(false)
  })

  it('destaque de status: mesmo status do Jira cresce, o resto desbota', () => {
    // aprovada e o épico estão "Em Desenvolvimento"; ajustes está em review.
    const marks = { highlightStatus: 'em desenvolvimento' }

    expect(nodeMarks(aprovada, marks)).toMatchObject({ emphasized: true, muted: false })
    expect(nodeMarks(ajustes, marks)).toMatchObject({ emphasized: false, muted: true })
  })

  it('pai e card fora da sprint também entram no destaque', () => {
    expect(nodeMarks(epico, { highlightStatus: 'Em Desenvolvimento' })).toMatchObject({ emphasized: true, muted: false })
    expect(nodeMarks(epico, { highlightStatus: 'DISPONIVEL PARA REVIEW' })).toMatchObject({ emphasized: false, muted: true })
  })
})

// --- marcador no canto do card -----------------------------------------------------

describe('marcador de PR no canto do card', () => {
  function mountNode(status, extra = {}) {
    return mount(IssueNode, {
      props: { data: { issue: { ...issue('WAI-9', { status }), ...extra }, selected: false } },
      global: { stubs: { Handle: true } },
    })
  }

  it.each([
    ['aprovada', 'var(--pr-approved)'],
    ['mergeada', 'var(--pr-merged)'],
    ['ajustes_requisitados', 'var(--pr-changes)'],
  ])('%s mostra o marcador na cor certa', (status, color) => {
    const wrapper = mountNode(status)
    const corner = wrapper.find('.node__corner')

    expect(corner.exists()).toBe(true)
    expect(corner.attributes('style')).toContain(color)
    expect(wrapper.attributes('data-corner')).toBe(status)
  })

  it.each(['sem_pr', 'pr_aberta', 'rascunho', 'branch_sem_pr'])('%s não marca o canto', (status) => {
    expect(mountNode(status).find('.node__corner').exists()).toBe(false)
  })

  it('card fora da sprint não marca o canto nem com PR aprovado', () => {
    expect(mountNode('aprovada', { in_sprint: false }).find('.node__corner').exists()).toBe(false)
  })
})

// --- legenda clicável --------------------------------------------------------------

// --- caixa de busca ----------------------------------------------------------------

describe('SprintSearch', () => {
  it('sem termo digitado só mostra o fechar', () => {
    const wrapper = mount(SprintSearch, { props: { modelValue: '', count: 0, position: 0 } })

    expect(wrapper.find('.find__count').exists()).toBe(false)
    expect(wrapper.findAll('.find__nav').map((b) => b.attributes('aria-label'))).toEqual(['Fechar busca'])
  })

  it('mostra a posição no total e desabilita a navegação com um resultado só', () => {
    const wrapper = mount(SprintSearch, { props: { modelValue: 'wai', count: 1, position: 1 } })

    expect(wrapper.find('.find__count').text()).toBe('1/1')
    expect(wrapper.findAll('.find__nav').slice(0, 2).every((b) => 'disabled' in b.attributes())).toBe(true)
  })

  it('termo sem resultado avisa na caixa', () => {
    const wrapper = mount(SprintSearch, { props: { modelValue: 'zzz', count: 0, position: 0 } })

    expect(wrapper.find('.find__count').text()).toBe('nada')
    expect(wrapper.find('.find--empty').exists()).toBe(true)
  })

  it('Enter vai para o próximo, Shift+Enter para o anterior e Esc fecha sem vazar para a janela', async () => {
    const wrapper = mount(SprintSearch, { props: { modelValue: 'wai', count: 3, position: 1 } })
    const input = wrapper.find('input')

    await input.trigger('keydown', { key: 'Enter' })
    await input.trigger('keydown', { key: 'Enter', shiftKey: true })
    const esc = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    const onWindow = vi.fn()
    window.addEventListener('keydown', onWindow)
    input.element.dispatchEvent(esc)
    window.removeEventListener('keydown', onWindow)

    expect(wrapper.emitted('next')).toHaveLength(1)
    expect(wrapper.emitted('prev')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
    // O painel da tarefa escuta Esc na janela: a busca não pode fechá-lo junto.
    expect(onWindow).not.toHaveBeenCalled()
  })
})

// --- câmera ------------------------------------------------------------------------

describe('SprintCanvas: foco da câmera', () => {
  const tree = { sprint: {}, nodes: [], edges: [], groups: [] }

  /**
   * O Vue Flow de verdade não inicializa em jsdom (depende de medida e de d3), então
   * o stub entrega a instância pelo `pane-ready` — que é justamente o caminho que o
   * componente usa para pegar a câmera.
   */
  function mountCanvas(props = {}) {
    const fitView = vi.fn()
    const VueFlowStub = {
      name: 'VueFlow',
      emits: ['pane-ready', 'node-click', 'pane-click'],
      template: '<div class="flow-stub"><slot /></div>',
    }
    const wrapper = mount(SprintCanvas, {
      props: { tree, ...props },
      global: {
        stubs: {
          VueFlow: VueFlowStub,
          Background: true,
          Controls: true,
          IssueNode: true,
          GroupFrameNode: true,
        },
      },
    })
    wrapper.findComponent(VueFlowStub).vm.$emit('pane-ready', { fitView })
    return { wrapper, fitView }
  }

  it('andar para o próximo resultado enquadra aquele card', async () => {
    const { wrapper, fitView } = mountCanvas({ focusKey: null })

    await wrapper.setProps({ focusKey: 'WAI-7' })
    await flushPromises()

    expect(fitView).toHaveBeenCalledWith(expect.objectContaining({ nodes: ['WAI-7'] }))
  })

  it('com a medida do card, centraliza na parte visível, descontando a coluna da direita', async () => {
    const setViewport = vi.fn()
    const node = { computedPosition: { x: 1000, y: 400 }, dimensions: { width: 236, height: 132 } }
    const VueFlowStub = { name: 'VueFlow', emits: ['pane-ready', 'node-click', 'pane-click'], template: '<div />' }
    const wrapper = mount(SprintCanvas, {
      props: { tree, rightInset: 500 },
      global: { stubs: { VueFlow: VueFlowStub, Background: true, Controls: true } },
    })
    wrapper.findComponent(VueFlowStub).vm.$emit('pane-ready', {
      fitView: vi.fn(),
      setViewport,
      findNode: (id) => (id === 'WAI-9' ? node : undefined),
      dimensions: ref({ width: 1500, height: 800 }),
    })

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('node-click', { node: { id: 'WAI-9', type: 'issue' } })
    // Quem move a câmera é a tarefa aberta, e é a tela que abre: o clique só avisa.
    await wrapper.setProps({ selectedKey: 'WAI-9' })
    await flushPromises()

    // Área visível: 1500 - 500 = 1000 px; o centro do card (1118, 466) vai para (500, 400).
    expect(setViewport).toHaveBeenCalledWith({ x: 500 - 1118, y: 400 - 466, zoom: 1 }, { duration: 320 })
  })

  describe('clique num card já à vista', () => {
    const node = { computedPosition: { x: 100, y: 100 }, dimensions: { width: 236, height: 132 } }

    async function openWithCamera(camera, { click = true, rightInset = 500 } = {}) {
      const setViewport = vi.fn()
      const VueFlowStub = { name: 'VueFlow', emits: ['pane-ready', 'node-click', 'pane-click'], template: '<div />' }
      const wrapper = mount(SprintCanvas, {
        props: { tree, rightInset },
        global: { stubs: { VueFlow: VueFlowStub, Background: true, Controls: true } },
      })
      wrapper.findComponent(VueFlowStub).vm.$emit('pane-ready', {
        fitView: vi.fn(),
        setViewport,
        findNode: () => node,
        dimensions: ref({ width: 1500, height: 800 }),
        viewport: ref(camera),
      })
      if (click) {
        wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('node-click', { node: { id: 'WAI-9', type: 'issue' } })
      }
      await wrapper.setProps({ selectedKey: 'WAI-9' })
      await flushPromises()
      return { wrapper, setViewport }
    }

    it('inteiro na área visível: seleciona sem mover a câmera', async () => {
      const { wrapper, setViewport } = await openWithCamera({ x: 0, y: 0, zoom: 1 })

      expect(wrapper.emitted('select').at(-1)).toEqual(['WAI-9'])
      expect(setViewport).not.toHaveBeenCalled()
    })

    it('cortado pela borda do canvas: centraliza', async () => {
      const { setViewport } = await openWithCamera({ x: -200, y: 0, zoom: 1 })

      expect(setViewport).toHaveBeenCalled()
    })

    it('atrás da coluna da direita: centraliza', async () => {
      // Card vai de 900 a 1136 px; a área visível acaba em 1500 - 500 = 1000.
      const { setViewport } = await openWithCamera({ x: 800, y: 0, zoom: 1 })

      expect(setViewport).toHaveBeenCalled()
    })

    it('tarefa aberta sem clique no canvas (notificação, busca global) também centraliza', async () => {
      const { setViewport } = await openWithCamera({ x: 800, y: 0, zoom: 1 }, { click: false })

      expect(setViewport).toHaveBeenCalled()
    })
  })

  it('clicar num card seleciona e enquadra o mesmo card', async () => {
    const { wrapper, fitView } = mountCanvas()

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('node-click', { node: { id: 'WAI-9', type: 'issue' } })
    await wrapper.setProps({ selectedKey: 'WAI-9' })
    await flushPromises()

    expect(wrapper.emitted('select').at(-1)).toEqual(['WAI-9'])
    expect(fitView).toHaveBeenCalledWith(expect.objectContaining({ nodes: ['WAI-9'] }))
  })

  it('Alt + clique num card pede o destaque do status dele, sem abrir nem mover a câmera', async () => {
    const { wrapper, fitView } = mountCanvas()
    const event = new MouseEvent('click', { altKey: true, cancelable: true })

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('node-click', {
      event,
      node: { id: 'WAI-9', type: 'issue', data: { issue: { key: 'WAI-9', status: 'Em Desenvolvimento' } } },
    })
    await flushPromises()

    expect(wrapper.emitted('highlight')).toEqual([['Em Desenvolvimento']])
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(fitView).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(true)
  })

  it('clique na moldura de grupo não seleciona nem move a câmera', async () => {
    const { wrapper, fitView } = mountCanvas()

    wrapper.findComponent({ name: 'VueFlow' }).vm.$emit('node-click', { node: { id: 'group:WAI-1', type: 'group-frame' } })
    await flushPromises()

    expect(wrapper.emitted('select')).toBeUndefined()
    expect(fitView).not.toHaveBeenCalled()
  })

  it('limpar a busca não mexe na câmera', async () => {
    const { wrapper, fitView } = mountCanvas({ focusKey: 'WAI-7' })
    fitView.mockClear()

    await wrapper.setProps({ focusKey: null })
    await flushPromises()

    expect(fitView).not.toHaveBeenCalled()
  })
})
