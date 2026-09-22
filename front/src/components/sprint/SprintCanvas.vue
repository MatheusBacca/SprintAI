<script setup>
import { computed, nextTick, provide, ref, unref, watch } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import GroupFrameNode from './GroupFrameNode.vue'
import IssueNode from './IssueNode.vue'
import WaveDividerNode from './WaveDividerNode.vue'
import { CANVAS_MARKS } from './canvasMarks'
import { layoutTree } from '@/utils/treeLayout'

const props = defineProps({
  tree: { type: Object, required: true },
  selectedKey: { type: String, default: null },
  /** Resultados da busca; todos ficam marcados. */
  matchKeys: { type: Array, default: () => [] },
  /** O resultado da vez: é nele que a câmera pousa. */
  focusKey: { type: String, default: null },
  /** Status do Jira em destaque (Alt + clique num card). `null` = sem destaque. */
  highlightStatus: { type: String, default: null },
  /** Largura, em px, coberta à direita pelo que flutua sobre o canvas (sprint e tarefa aberta). */
  rightInset: { type: Number, default: 0 },
})
const emit = defineEmits(['select', 'highlight'])

const flowId = 'sprint-tree'

/**
 * A câmera vem do `pane-ready`: é a instância que o próprio pane entrega, sem
 * depender de o `useVueFlow(id)` daqui de fora casar com o `<VueFlow :id>`. De
 * quebra é o que deixa o foco testável — o teste entrega a instância pelo evento,
 * já que o Vue Flow de verdade não inicializa em jsdom.
 */
const flow = ref(null)
const fitView = (options) => flow.value?.fitView(options)

const layout = computed(() => layoutTree(props.tree, { selectedKey: props.selectedKey }))

// Busca e filtro descem por inject: mexer no array de nós faria o Vue Flow
// recriar e remedir cada card a cada tecla — e sem medida o `fitView` não anda.
provide(
  CANVAS_MARKS,
  computed(() => ({
    matchKeys: props.matchKeys,
    focusKey: props.focusKey,
    highlightStatus: props.highlightStatus,
  })),
)

const FOCUS_ZOOM = 1
const FOCUS_DURATION = 320

/**
 * Pousa a câmera no card, centralizado na parte **visível** do canvas: a coluna da
 * direita (sprint e tarefa aberta) flutua por cima, e o centro do canvas inteiro deixaria
 * o card — e os vizinhos dele — escondidos atrás dela. O `fitView` não aceita
 * deslocamento, então a conta é feita à mão. Sem medida do card (ou da instância, em
 * teste), cai no `fitView` comum.
 */
async function focusNode(key, { onlyIfHidden = false } = {}) {
  if (!key) return
  await nextTick()
  const instance = flow.value
  const node = instance?.findNode?.(key)
  const viewport = unref(instance?.dimensions)
  const size = node?.dimensions
  if (onlyIfHidden && fullyVisible(node, viewport, unref(instance?.viewport))) return
  if (!instance?.setViewport || !node || !viewport?.width || !size?.width) {
    // `duration` faz a câmera deslizar até o card em vez de teleportar.
    fitView({ nodes: [key], padding: 0.4, maxZoom: 1.1, duration: FOCUS_DURATION })
    return
  }
  const position = node.computedPosition ?? node.position
  const visibleWidth = Math.max(viewport.width - props.rightInset, size.width * FOCUS_ZOOM)
  instance.setViewport(
    {
      x: visibleWidth / 2 - (position.x + size.width / 2) * FOCUS_ZOOM,
      y: viewport.height / 2 - (position.y + size.height / 2) * FOCUS_ZOOM,
      zoom: FOCUS_ZOOM,
    },
    { duration: FOCUS_DURATION },
  )
}

/**
 * O card cabe inteiro na parte visível do canvas, com a câmera de agora? A coluna da
 * direita conta como fora — é onde o painel da tarefa vai abrir. Sem medida (card,
 * pane ou câmera), responde não: na dúvida, enquadra.
 */
function fullyVisible(node, pane, camera) {
  const size = node?.dimensions
  if (!size?.width || !pane?.width || !camera?.zoom) return false
  const position = node.computedPosition ?? node.position
  const left = position.x * camera.zoom + camera.x
  const top = position.y * camera.zoom + camera.y
  return (
    left >= 0 &&
    top >= 0 &&
    left + size.width * camera.zoom <= pane.width - props.rightInset &&
    top + size.height * camera.zoom <= pane.height
  )
}

// Nova sprint (ou filtro de "só minhas"): reenquadra — a não ser que já exista um
// card em foco (link direto para a tarefa), que aí é nele que a câmera pousa.
watch(
  () => props.tree,
  async () => {
    await nextTick()
    setTimeout(() => {
      const key = props.focusKey ?? props.selectedKey
      if (key) focusNode(key)
      else fitView({ padding: 0.12, maxZoom: 1 })
    }, 50)
  },
)

// Andar pelos resultados da busca move a câmera.
watch(() => props.focusKey, (key) => focusNode(key))

/**
 * Pedido do dev: abrir a tarefa centraliza o card na área visível quando ele está
 * cortado ou atrás da coluna da direita. Já inteiro à vista, a câmera fica onde está —
 * pular a cada clique faz perder o lugar no canvas.
 *
 * Fica no `selectedKey` e não no clique do card porque a tarefa também é aberta de fora
 * do canvas — pela busca global e pela notificação de tarefa do sino, que chegam com a
 * árvore já desenhada e sem clique nenhum para reagir.
 */
watch(() => props.selectedKey, (key) => focusNode(key, { onlyIfHidden: true }))

function onNodeClick({ event, node }) {
  if (node.type !== 'issue') return
  // Alt + clique destaca os cards no mesmo status do Jira, sem abrir a tarefa nem
  // mover a câmera — é para olhar o canvas inteiro.
  if (event?.altKey) {
    event.preventDefault()
    emit('highlight', node.data.issue.status)
    return
  }
  emit('select', node.id)
}
</script>

<template>
  <VueFlow
    :id="flowId"
    class="canvas"
    :nodes="layout.nodes"
    :edges="layout.edges"
    :nodes-draggable="false"
    :nodes-connectable="false"
    :min-zoom="0.15"
    :max-zoom="1.6"
    :fit-view-on-init="true"
    :default-edge-options="{ zIndex: 0 }"
    @pane-ready="flow = $event"
    @node-click="onNodeClick"
    @pane-click="emit('select', null)"
  >
    <template #node-issue="nodeProps">
      <IssueNode v-bind="nodeProps" />
    </template>
    <template #node-group-frame="nodeProps">
      <GroupFrameNode v-bind="nodeProps" />
    </template>
    <template #node-wave-divider="nodeProps">
      <WaveDividerNode v-bind="nodeProps" />
    </template>
    <Background :gap="18" :size="1" />
    <Controls position="bottom-right" :show-interactive="false" />
  </VueFlow>
</template>

<style scoped>
.canvas {
  width: 100%;
  height: 100%;
}

/*
 * O pontilhado do fundo é um <circle> com fill de atributo — qualquer regra
 * CSS ganha dele, e é assim que ele acompanha o tema (a prop pattern-color
 * receberia um hex fixo).
 */
.canvas :deep(.vue-flow__background circle) {
  fill: var(--color-canvas-dots);
}

/* Os controles de zoom vêm brancos do @vue-flow/controls — um bloco aceso
   no meio do canvas escuro. */
.canvas :deep(.vue-flow__controls-button) {
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  fill: var(--color-text-secondary);
}

.canvas :deep(.vue-flow__controls-button:hover) {
  background: var(--color-surface-hover);
  fill: var(--color-text);
}

.canvas :deep(.vue-flow__node-group-frame),
.canvas :deep(.vue-flow__node-wave-divider) {
  pointer-events: none;
}

.canvas :deep(.edge--parent path.vue-flow__edge-path) {
  stroke: var(--pr-open);
  stroke-width: 1.5;
}

.canvas :deep(.edge--link path.vue-flow__edge-path) {
  stroke: var(--color-primary);
  stroke-width: 1.5;
  stroke-dasharray: 6 4;
}

.canvas :deep(.edge--blocks path.vue-flow__edge-path) {
  stroke: var(--color-error);
  stroke-width: 1.8;
}

.canvas :deep(.edge--blocks .vue-flow__edge-textbg) {
  fill: var(--color-error-surface);
}

.canvas :deep(.edge--blocks .vue-flow__edge-text) {
  fill: var(--color-error);
  font-size: 11px;
  font-weight: 600;
}
</style>
