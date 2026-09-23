<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import PullRequestLinks from './PullRequestLinks.vue'
import StatusFlowPicker from './StatusFlowPicker.vue'
import StoryPointsEditor from './StoryPointsEditor.vue'
import { useJiraActionsStore } from '@/stores/jiraActions'

/**
 * O painel das ações no Jira, um só para o app, ancorado no chip clicado (status, SP ou
 * badge de PR). Vai para o `body` porque o chip pode estar dentro do canvas — que tem
 * transform de zoom e corta o que vaza — ou do painel lateral, que rola.
 *
 * O painel segue o chip: rolar, dar zoom no canvas ou redimensionar a janela remede o
 * chip e reposiciona. Fechar a cada `scroll` não servia — o clique foca o chip, o foco
 * rola o contêiner uns pixels para mostrá-lo, e o painel fechava no mesmo clique que o
 * abriu. Só fecha quando o chip sai da tela.
 */
const store = useJiraActionsStore()
const panel = ref(null)
const anchorRect = ref(null)
const position = ref({ top: -9999, left: -9999, maxHeight: null })

const GAP = 6
const MARGIN = 8

const label = computed(() => {
  const open = store.open
  if (!open) return null
  if (open.kind === 'status') return `Mover ${open.issueKey} no Jira`
  if (open.kind === 'points') return `Story Points de ${open.issueKey}`
  return 'PRs no Bitbucket'
})

/**
 * Embaixo do chip; não cabendo, em cima; não cabendo em lugar nenhum, no lado com mais
 * espaço e rolando por dentro. Nunca por cima do próprio chip nem vazando da janela.
 */
function place() {
  const rect = anchorRect.value
  const el = panel.value
  if (!rect || !el) return
  const width = el.offsetWidth
  // Altura do conteúdo inteiro, mesmo com o painel já limitado por `max-height`.
  const natural = el.scrollHeight + (el.offsetHeight - el.clientHeight)
  const below = window.innerHeight - MARGIN - (rect.bottom + GAP)
  const above = rect.top - GAP - MARGIN
  const downward = natural <= below || below >= above
  const maxHeight = Math.max(downward ? below : above, 120)
  const top = downward ? rect.bottom + GAP : rect.top - GAP - Math.min(natural, maxHeight)
  const left = Math.min(Math.max(rect.left, MARGIN), window.innerWidth - MARGIN - width)
  position.value = { top, left: Math.max(MARGIN, left), maxHeight }
}

function snapshot(rect) {
  const { top, left, right, bottom, width, height } = rect
  return { top, left, right, bottom, width, height }
}

let frame = 0
/** Remede o chip no próximo quadro (depois do scroll/zoom aplicado) e acompanha. */
function follow() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    const anchor = store.open?.anchor
    // Chip remontado (a árvore recarregou): fica onde estava, que é onde o card está.
    if (!anchor?.isConnected) return
    const rect = anchor.getBoundingClientRect()
    const gone = rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth
    if (gone) {
      store.close()
      return
    }
    anchorRect.value = snapshot(rect)
    place()
  })
}

let observer = null
watch(
  () => store.open,
  async (open) => {
    observer?.disconnect()
    if (!open) return
    anchorRect.value = open.rect
    await nextTick()
    place()
    // O conteúdo muda de altura (o fluxo chega do Jira depois de abrir): reposiciona.
    if (typeof ResizeObserver !== 'undefined' && panel.value) {
      observer = new ResizeObserver(place)
      observer.observe(panel.value)
    }
  },
)

function inside(target) {
  return Boolean(panel.value?.contains(target) || store.open?.anchor?.contains?.(target))
}

// Clique no próprio chip não fecha aqui: o clique dele é que alterna o painel.
function onPointerDown(event) {
  if (store.open && !inside(event.target)) store.close()
}

function onKeydown(event) {
  if (event.key !== 'Escape' || !store.open) return
  // Esc fecha só o painel — sem isto, o mesmo Esc fecharia o painel da tarefa por baixo.
  event.stopPropagation()
  const anchor = store.open.anchor
  store.close()
  if (anchor?.isConnected) anchor.focus()
}

// Rolar a lista do próprio painel não mexe no chip.
function onScrollOrWheel(event) {
  if (store.open && !panel.value?.contains(event.target)) follow()
}

function onResize() {
  if (store.open) follow()
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown, true)
  window.addEventListener('keydown', onKeydown, true)
  window.addEventListener('scroll', onScrollOrWheel, true)
  window.addEventListener('wheel', onScrollOrWheel, { capture: true, passive: true })
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  document.removeEventListener('pointerdown', onPointerDown, true)
  window.removeEventListener('keydown', onKeydown, true)
  window.removeEventListener('scroll', onScrollOrWheel, true)
  window.removeEventListener('wheel', onScrollOrWheel, { capture: true })
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <Teleport to="body">
    <section
      v-if="store.open"
      ref="panel"
      class="jira-popover card"
      role="dialog"
      :aria-label="label"
      :data-kind="store.open.kind"
      :style="{
        top: `${position.top}px`,
        left: `${position.left}px`,
        maxHeight: position.maxHeight ? `${position.maxHeight}px` : null,
      }"
    >
      <StatusFlowPicker v-if="store.open.kind === 'status'" :issue-key="store.open.issueKey" />
      <StoryPointsEditor
        v-else-if="store.open.kind === 'points'"
        :key="store.open.issueKey"
        :issue-key="store.open.issueKey"
        :points="store.open.points"
      />
      <PullRequestLinks v-else :links="store.open.links" :issue-key="store.open.issueKey" />
    </section>
  </Teleport>
</template>

<style scoped>
.jira-popover {
  position: fixed;
  z-index: var(--z-popover);
  overflow-y: auto;
  padding: var(--space-3);
  box-shadow: var(--shadow-modal);
}
</style>
