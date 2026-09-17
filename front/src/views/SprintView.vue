<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { normalize } from '@/utils/highlight'
import { CalendarRange, ChevronLeft, ChevronRight, RefreshCw, X } from 'lucide-vue-next'

import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import SprintCanvas from '@/components/sprint/SprintCanvas.vue'
import SprintSearch from '@/components/sprint/SprintSearch.vue'
import { useIssueDetailStore } from '@/stores/issueDetail'
import { useNotesStore } from '@/stores/notes'
import { useScreenContextStore } from '@/stores/screenContext'
import { useSprintBoardStore } from '@/stores/sprintBoard'
import { useRefreshStore } from '@/stores/refresh'
import { useSyncStore } from '@/stores/sync'

const route = useRoute()
const router = useRouter()
const board = useSprintBoardStore()
const refresh = useRefreshStore()
const sync = useSyncStore()
const screen = useScreenContextStore()
const issueDetail = useIssueDetailStore()
const notes = useNotesStore()

const STATE_LABEL = { active: 'Ativas', future: 'Futuras', closed: 'Fechadas' }

const sprintId = computed(() => Number(route.query.sprint) || board.defaultSprintId)
const selectedKey = computed(() => route.query.tarefa ?? null)
const sprint = computed(() => board.tree?.sprint ?? board.sprints.find((s) => s.id === sprintId.value))
const counters = computed(() => board.tree?.counters ?? null)
// Com o escopo "só as minhas" o espelho já só tem tarefas suas: o filtro não faz sentido.
const showMineFilter = computed(() => sync.scope?.jira?.assignee_scope === 'all')

const dateFormat = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short' })
const period = computed(() => {
  const s = sprint.value
  if (!s?.start_date) return null
  const end = s.complete_date ?? s.end_date
  return `${dateFormat.format(new Date(s.start_date))} – ${end ? dateFormat.format(new Date(end)) : '…'}`
})

// --- Navegação entre sprints --------------------------------------------------

/**
 * Ordem cronológica para as setas: anterior é a que começou antes. Sprint futura sem
 * data vai para o fim — é a próxima a ser planejada, não uma do passado.
 */
const timeline = computed(() =>
  [...board.sprints].sort((a, b) => {
    const at = a.start_date ? Date.parse(a.start_date) : Infinity
    const bt = b.start_date ? Date.parse(b.start_date) : Infinity
    return at - bt || a.id - b.id
  }),
)
const position = computed(() => timeline.value.findIndex((s) => s.id === sprintId.value))
const previousSprint = computed(() => (position.value > 0 ? timeline.value[position.value - 1] : null))
const nextSprint = computed(() => (position.value >= 0 ? (timeline.value[position.value + 1] ?? null) : null))

// Antes dos watches imediatos abaixo, que já publicam sprint e tarefa em foco.
screen.enter('sprint')

onMounted(async () => {
  sync.loadScope().catch(() => {})
  window.addEventListener('keydown', onFindShortcut)
  await board.loadSprints()
})

onBeforeUnmount(() => {
  screen.enter(null)
  window.removeEventListener('keydown', onFindShortcut)
  overlayObserver?.disconnect()
})

// --- Área visível do canvas ----------------------------------------------------

/**
 * Quanto da direita do canvas a coluna flutuante cobre (largura + margens). O canvas
 * usa para centralizar o card aberto no que sobra — a coluna muda de largura com a
 * janela, por isso é medida e não calculada.
 */
const overlay = ref(null)
const rightInset = ref(0)
let overlayObserver = null

function measureOverlay() {
  const el = overlay.value
  if (!el) return
  const pageRight = el.offsetParent?.getBoundingClientRect().right ?? 0
  const { left } = el.getBoundingClientRect()
  rightInset.value = Math.max(0, Math.round(pageRight - left))
}

onMounted(() => {
  measureOverlay()
  if (typeof ResizeObserver !== 'undefined' && overlay.value) {
    overlayObserver = new ResizeObserver(measureOverlay)
    overlayObserver.observe(overlay.value)
  }
})

watch(
  [sprintId, () => board.onlyMine],
  ([id]) => {
    if (!id) return
    screen.$patch({ sprintId: id })
    board.loadTree(id)
  },
  { immediate: true },
)

watch(
  () => board.tree,
  (tree) => {
    screen.$patch({ visibleIssueKeys: tree ? tree.nodes.filter((n) => n.in_sprint).map((n) => n.key) : [] })
  },
)

watch(selectedKey, (key) => screen.focusIssue(key), { immediate: true })

// Card aberto apaga a bolinha de atualização. Olha a árvore também: o link direto
// chega antes dela, e um sync com o painel aberto traz a mudança que o dev está vendo.
watch(
  [selectedKey, () => board.tree],
  ([key]) => {
    if (key) board.markSeen(key)
  },
  { immediate: true },
)

// --- Busca no canvas ---------------------------------------------------------

const term = ref('')
const matchIndex = ref(0)

/**
 * Casa por chave ou título, sem acento nem caixa — as mesmas regras da busca
 * global, para não haver duas noções de "achou" no app.
 */
const matches = computed(() => {
  const needle = normalize(term.value.trim())
  if (needle.length < 2 || !board.tree) return []
  return board.tree.nodes
    .filter((n) => normalize(`${n.key} ${n.summary ?? ''}`).includes(needle))
    .map((n) => n.key)
})

const focusKey = computed(() => matches.value[matchIndex.value] ?? null)

// Termo novo: volta para o primeiro resultado.
watch(term, () => (matchIndex.value = 0))
// A árvore mudou (outra sprint, sync): o índice antigo pode não existir mais.
watch(matches, (list) => {
  if (matchIndex.value >= list.length) matchIndex.value = 0
})

function step(delta) {
  const total = matches.value.length
  if (!total) return
  matchIndex.value = (matchIndex.value + delta + total) % total
}

const searchOpen = ref(false)
const searchBox = ref(null)

async function openSearch() {
  searchOpen.value = true
  await nextTick()
  searchBox.value?.focus()
}

// Fechar também limpa: resultado marcado sem a caixa à vista seria um mistério no canvas.
function closeSearch() {
  searchOpen.value = false
  term.value = ''
  matchIndex.value = 0
}

/**
 * Ctrl+F abre a busca do canvas no lugar da do navegador, que não acha nada dentro dos
 * cards. Com um diálogo aberto (editor de lembrete, busca global) o atalho fica com ele.
 */
function onFindShortcut(event) {
  const isFind = (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'f'
  if (!isFind || document.querySelector('[aria-modal="true"]')) return
  event.preventDefault()
  openSearch()
}

// --- Destaque por status (Alt + clique num card) -----------------------------

const highlightStatus = ref(null)

// O mesmo Alt + clique no mesmo status desfaz, como um interruptor.
function toggleHighlight(status) {
  highlightStatus.value = highlightStatus.value === status ? null : status
}

// Outra sprint tem outros cards: o destaque da anterior não vale mais.
watch(sprintId, () => (highlightStatus.value = null))

// Sync concluído ou Recarregar: árvore e painel aberto se refazem.
watch(() => refresh.revision, () => {
  board.loadSprints()
  if (sprintId.value) board.loadTree(sprintId.value)
  if (selectedKey.value) issueDetail.load(selectedKey.value)
})

// Lembrete criado, arquivado ou apagado muda a contagem do rodapé dos cards.
watch(() => notes.revision, () => {
  if (sprintId.value) board.loadTree(sprintId.value)
})

// --- Entrada do painel da tarefa ----------------------------------------------

/**
 * Depois de entrar, o painel fica: trocar de tarefa com ele aberto carrega no lugar. Só
 * fechar zera. Se a resposta demorar demais, entra assim mesmo com o "Carregando…" —
 * painel que nunca aparece seria pior que um que chega aos poucos.
 */
const drawerRevealed = ref(false)
const REVEAL_TIMEOUT = 1500
let revealTimer = null

watch(
  selectedKey,
  (key) => {
    clearTimeout(revealTimer)
    if (!key) {
      drawerRevealed.value = false
      return
    }
    if (!drawerRevealed.value) revealTimer = setTimeout(() => (drawerRevealed.value = true), REVEAL_TIMEOUT)
  },
  { immediate: true },
)
onBeforeUnmount(() => clearTimeout(revealTimer))

function goToSprint(id) {
  if (id) router.replace({ query: { ...route.query, sprint: String(id), tarefa: undefined } })
}

function selectIssue(key) {
  router.replace({ query: { ...route.query, tarefa: key ?? undefined } })
}
</script>

<template>
  <div class="sprint-page">
    <!-- O canvas ocupa a tela inteira; sprint e tarefa aberta flutuam por cima, à direita. -->
    <div class="sprint__canvas card">
      <div v-if="board.sprintsError || board.treeError" class="sprint__empty" role="alert">
        {{ board.sprintsError || board.treeError }}
      </div>
      <div v-else-if="!board.sprintsLoading && !board.sprints.length" class="sprint__empty">
        <p>Nenhuma sprint no espelho local ainda.</p>
        <RouterLink to="/configuracoes?aba=sincronizacao" class="btn btn--primary">Configurar sincronização</RouterLink>
      </div>
      <div v-else-if="board.tree && !board.tree.nodes.length" class="sprint__empty">
        <p>Nenhuma tarefa nesta sprint{{ board.onlyMine ? ' atribuída a você' : '' }}.</p>
      </div>
      <SprintCanvas
        v-else-if="board.tree"
        :tree="board.tree"
        :selected-key="selectedKey"
        :match-keys="matches"
        :focus-key="focusKey"
        :highlight-status="highlightStatus"
        :right-inset="rightInset"
        @select="selectIssue"
        @highlight="toggleHighlight"
      />
      <div v-else class="sprint__empty muted">Carregando árvore…</div>
    </div>

    <!-- Ctrl+F: fora do card da sprint, alinhada ao topo dele, no espaço livre ao lado. -->
    <div v-if="searchOpen" class="sprint__find card">
      <SprintSearch
        ref="searchBox"
        v-model="term"
        :count="matches.length"
        :position="matches.length ? matchIndex + 1 : 0"
        @next="step(1)"
        @prev="step(-1)"
        @close="closeSearch"
      />
    </div>

    <div ref="overlay" class="sprint__overlay">
      <header class="sprint__panel card">
        <div class="sprint__top">
          <div class="sprint__nav" :data-state="sprint?.state">
            <button
              type="button"
              class="sprint__arrow"
              :disabled="!previousSprint"
              :title="previousSprint ? `Sprint anterior: ${previousSprint.name}` : 'Nenhuma sprint anterior'"
              aria-label="Sprint anterior"
              @click="goToSprint(previousSprint?.id)"
            >
              <ChevronLeft :size="16" />
            </button>
            <div class="sprint__current">
              <select
                class="sprint__select"
                :value="sprintId ?? ''"
                :disabled="!board.sprints.length"
                :title="sprint?.goal || sprint?.name"
                aria-label="Sprint"
                @change="goToSprint($event.target.value)"
              >
                <optgroup v-for="(list, state) in board.grouped" v-show="list.length" :key="state" :label="STATE_LABEL[state]">
                  <option v-for="s in list" :key="s.id" :value="s.id">{{ s.name }} ({{ s.issue_count }})</option>
                </optgroup>
              </select>
              <!-- Resumo da sprint dentro do próprio seletor: período, concluídas e SP. -->
              <p v-if="period || counters" class="sprint__summary">
                <span v-if="period"><CalendarRange :size="11" /> {{ period }}</span>
                <template v-if="counters">
                  <span>{{ counters.done }}/{{ counters.tasks }} concluídas</span>
                  <span>{{ counters.story_points }} SP</span>
                </template>
              </p>
            </div>
            <button
              type="button"
              class="sprint__arrow"
              :disabled="!nextSprint"
              :title="nextSprint ? `Próxima sprint: ${nextSprint.name}` : 'Nenhuma sprint posterior'"
              aria-label="Próxima sprint"
              @click="goToSprint(nextSprint?.id)"
            >
              <ChevronRight :size="16" />
            </button>
          </div>

          <button type="button" class="btn btn--secondary sprint__reload" :disabled="board.treeLoading || !sprintId" title="Recarregar tudo: árvore, painel aberto e as outras telas" @click="refresh.reload()">
            <RefreshCw :size="14" :class="{ spin: board.treeLoading }" />
          </button>
        </div>

        <p v-if="sprint?.goal" class="sprint__goal" :title="sprint.goal">{{ sprint.goal }}</p>

        <label v-if="showMineFilter" class="sprint__mine"><input v-model="board.onlyMine" type="checkbox"> Só minhas</label>

        <p v-if="highlightStatus" class="sprint__highlight">
          Destacando <strong>{{ highlightStatus }}</strong>
          <button type="button" aria-label="Limpar destaque" title="Limpar destaque" @click="highlightStatus = null"><X :size="12" /></button>
        </p>
      </header>

      <!-- O painel monta escondido fora da tela e só desliza da direita quando a tarefa
           inteira chegou; fechar desliza de volta. Trocar de tarefa com ele aberto não anima. -->
      <Transition name="drawer-slide">
        <IssueDrawer
          v-if="selectedKey"
          class="sprint__drawer"
          :class="{ 'sprint__drawer--revealed': drawerRevealed }"
          :issue-key="selectedKey"
          @close="selectIssue(null)"
          @open="selectIssue"
          @ready="drawerRevealed = true"
        />
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.sprint-page {
  /* Largura da coluna flutuante; a busca do Ctrl+F se posiciona a partir dela. */
  --overlay-width: min(480px, calc(100% - 2 * var(--space-3)));

  position: relative;
  height: 100%;
  min-height: 420px;
  overflow: hidden;
}

.sprint__canvas {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

/* Coluna flutuante: o vazio abaixo do painel não pode roubar clique do canvas. */
.sprint__overlay {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  bottom: var(--space-3);
  z-index: 5;
  width: var(--overlay-width);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  pointer-events: none;
}

.sprint__overlay > * {
  pointer-events: auto;
}

/* Colada no card da sprint, do lado de fora: a coluna já encosta na borda direita da
   tela, então a busca fica no espaço livre do canvas ao lado dela — e nunca mais larga
   que esse espaço, senão vazaria por cima do menu em tela estreita. */
.sprint__find {
  position: absolute;
  top: var(--space-3);
  right: calc(var(--overlay-width) + 2 * var(--space-3));
  z-index: 5;
  box-sizing: border-box;
  width: min(360px, calc(100% - var(--overlay-width) - 3 * var(--space-3)));
  padding: 4px;
  box-shadow: var(--shadow-modal);
}

.sprint__find :deep(.find) {
  width: 100%;
  border-color: transparent;
}

.sprint__panel {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  box-shadow: var(--shadow-modal);
}

/* Especificidade de duas classes: o painel da tarefa tem largura própria quando fica
   ao lado das outras telas; aqui ele ocupa a coluna e o resto da altura. */
.sprint__overlay .sprint__drawer {
  flex: 1;
  width: 100%;
  min-width: 0;
  min-height: 0;
  box-shadow: var(--shadow-modal);
}

/* Escondido à direita da tela até a tarefa inteira chegar; aí desliza para o lugar num
   só movimento. A página corta o que passa da borda, senão a entrada criaria rolagem. */
.sprint__overlay .sprint__drawer {
  transform: translateX(calc(100% + 2 * var(--space-3)));
  opacity: 0;
  pointer-events: none;
  transition:
    transform 0.34s cubic-bezier(0.2, 0.8, 0.2, 1),
    opacity 0.2s ease-out;
}

.sprint__overlay .sprint__drawer--revealed {
  transform: none;
  opacity: 1;
  pointer-events: auto;
}

.sprint__overlay .sprint__drawer.drawer-slide-leave-active {
  transition:
    transform 0.26s cubic-bezier(0.4, 0, 0.8, 0.4),
    opacity 0.26s ease-in;
}

.sprint__overlay .sprint__drawer.drawer-slide-leave-to {
  transform: translateX(calc(100% + 2 * var(--space-3)));
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .sprint__overlay .sprint__drawer {
    transition: none;
  }
}

.sprint__top {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* Sprint ativa em verde; as outras (passadas e futuras) em roxo. */
.sprint__nav {
  --nav-color: var(--color-primary);
  --nav-bg: var(--color-primary-soft);

  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-md);
  background: var(--nav-bg);
  color: var(--nav-color);
}

.sprint__nav[data-state='active'] {
  --nav-color: var(--color-success);
  --nav-bg: var(--color-success-surface-soft);

  box-shadow: 0 0 0 1px var(--color-success-border) inset;
}

.sprint__arrow {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: inherit;
}

.sprint__arrow:hover:not(:disabled) {
  background: var(--color-surface-hover);
}

.sprint__arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

.sprint__current {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 2px 0;
}

.sprint__summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 2px 10px;
  margin: 0;
  font-size: 11px;
  font-weight: 500;
  color: inherit;
  opacity: 0.85;
}

.sprint__summary span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}

.sprint__select {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  font: inherit;
  font-size: var(--text-sm);
  font-weight: 600;
  color: inherit;
  text-align: center;
  text-overflow: ellipsis;
  cursor: pointer;
}

.sprint__reload {
  flex-shrink: 0;
}

.sprint__goal {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
  font-weight: 600;
}

.sprint__mine {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.sprint__highlight {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.sprint__highlight button {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--color-surface-muted);
  color: inherit;
}

.sprint__empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-6);
  color: var(--color-text-secondary);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
