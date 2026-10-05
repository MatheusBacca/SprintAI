<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Columns2, FolderGit2, GitGraph, RefreshCw, Workflow, X } from 'lucide-vue-next'

import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import SprintCanvas from '@/components/sprint/SprintCanvas.vue'
import InvolvedRepos from '@/components/workspace/InvolvedRepos.vue'
import RepoTimeline from '@/components/workspace/RepoTimeline.vue'
import TerminalDock from '@/components/workspace/TerminalDock.vue'
import WorkspaceStart from '@/components/workspace/WorkspaceStart.vue'
import WorkspaceTabs from '@/components/workspace/WorkspaceTabs.vue'
import { useNotesStore } from '@/stores/notes'
import { useRefreshStore } from '@/stores/refresh'
import { useScreenContextStore } from '@/stores/screenContext'
import { useWorkspaceStore } from '@/stores/workspace'
import { useWorkspaceReposStore } from '@/stores/workspaceRepos'
import { NODE_WIDTH } from '@/utils/treeLayout'

/**
 * Workspace (`/workspace?ws=<id>`): a feature numa aba. Estado na URL, como na Sprint —
 * `ws` é o workspace, `aba` a área principal (`tarefas` | `linha` | `lado`, as duas lado a
 * lado), `repo` o repositório da linha do tempo e `tarefa` o painel aberto.
 *
 * A tarefa e os repositórios envolvidos ficam no painel da direita, o mesmo das outras telas:
 * a aba Detalhes ganha a lista de repositórios só aqui (slot `details`).
 */
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const localRepos = useWorkspaceReposStore()
const refresh = useRefreshStore()
const notes = useNotesStore()
const screen = useScreenContextStore()

const workspaceId = computed(() => Number(route.query.ws) || null)
const selectedKey = computed(() => route.query.tarefa ?? null)
const current = computed(() => (workspaceId.value ? store.list.find((w) => w.id === workspaceId.value) ?? null : null))
const isIssue = computed(() => current.value?.kind === 'issue')
const rootKey = computed(() => current.value?.root_issue_key ?? null)

// --- Área principal: a última escolhida fica salva neste navegador -------------------------

const VIEWS = ['tarefas', 'linha', 'lado']
const VIEW_KEY = 'sprintai.workspace.view'

function readView() {
  try {
    const saved = localStorage.getItem(VIEW_KEY)
    if (VIEWS.includes(saved)) return saved
  } catch {
    // Sem localStorage (janela anônima, teste): começa nas tarefas.
  }
  return 'tarefas'
}

const savedView = ref(readView())
/** A da URL manda (link colado, voltar do navegador); sem ela, a última que o dev escolheu. */
const view = computed(() => {
  if (!isIssue.value) return 'linha'
  return VIEWS.includes(route.query.aba) ? route.query.aba : savedView.value
})
const showTimeline = computed(() => view.value !== 'tarefas')

/**
 * Só o clique nas abas grava. Escolher um repo leva à linha do tempo sem mudar a
 * preferência: é um pulo para olhar o repo, não a tela com que o dev quer abrir.
 */
function chooseView(value) {
  savedView.value = value
  try {
    localStorage.setItem(VIEW_KEY, value)
  } catch {
    // idem
  }
  patchQuery({ aba: value })
}

/** Repo da linha do tempo: o da URL, senão o primeiro com clone local. */
const selectedRepo = computed(() => {
  const local = store.visibleRepos.filter((r) => r.local)
  const wanted = route.query.repo
  return local.find((r) => r.slug === wanted)?.slug ?? local[0]?.slug ?? null
})

const addable = computed(() => {
  const listed = new Set((store.detail?.repos ?? []).map((r) => r.slug))
  return localRepos.gitRepos.map((r) => r.slug).filter((slug) => !listed.has(slug))
})

const localVisibleRepos = computed(() => store.visibleRepos.filter((r) => r.local))
const allLocalRepos = computed(() => localRepos.gitRepos.map((r) => ({ slug: r.slug, path: r.path })))

// --- Terminais: altura e recolhido são conveniência deste navegador -----------------------

const DOCK_KEY = 'sprintai.workspace.dock'
const DOCK_MIN = 140

function readDock() {
  try {
    const saved = JSON.parse(localStorage.getItem(DOCK_KEY) ?? 'null')
    if (saved && typeof saved.height === 'number') return { height: saved.height, collapsed: Boolean(saved.collapsed) }
  } catch {
    // Sem localStorage (janela anônima, teste): fica o padrão.
  }
  return { height: 300, collapsed: false }
}

const dock = ref(readDock())
watch(
  dock,
  (value) => {
    try {
      localStorage.setItem(DOCK_KEY, JSON.stringify(value))
    } catch {
      // idem
    }
  },
  { deep: true },
)

function startDockResize(event) {
  const startY = event.clientY
  const startHeight = dock.value.height
  const max = Math.max(DOCK_MIN, window.innerHeight - 260)
  const move = (e) => {
    dock.value.height = Math.min(max, Math.max(DOCK_MIN, startHeight + (startY - e.clientY)))
  }
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
}

/** Chaves da feature: a linha do tempo destaca as branches delas (e as do card aberto). */
const featureKeys = computed(() => store.detail?.keys ?? [])
const highlightKeys = computed(() => (selectedKey.value ? [selectedKey.value] : []))
/** Repos da tarefa aberta no painel — os terminais deles vêm para a frente. */
const focusRepos = computed(() =>
  selectedKey.value ? store.visibleRepos.filter((r) => r.issue_keys.includes(selectedKey.value)).map((r) => r.slug) : [],
)

/** A tarefa e as filhas dela no canvas da feature (pai direto e por link de hierarquia). */
function subtreeKeys(key) {
  const byKey = new Map((store.tree?.nodes ?? []).map((n) => [n.key, n]))
  const seen = new Set([key])
  const queue = [key]
  while (queue.length) {
    const node = byKey.get(queue.shift())
    for (const child of [...(node?.children ?? []), ...(node?.co_children ?? [])]) {
      if (seen.has(child)) continue
      seen.add(child)
      queue.push(child)
    }
  }
  return seen
}

/**
 * "Repositórios envolvidos" na aba Detalhes do painel. Na tarefa raiz, a lista do workspace
 * inteiro, com adicionar e escondidos — era a coluna da esquerda. Numa tarefa da feature, só
 * os repos dela e das filhas dela: o Épico mostra os das suas tarefas. Tarefa de fora da
 * feature (um link aberto do próprio painel) fica sem a seção.
 */
const drawerRepos = computed(() => {
  const key = selectedKey.value
  if (!key || !isIssue.value) return null
  if (key === rootKey.value) return { repos: store.visibleRepos, root: true }
  if (!featureKeys.value.includes(key)) return null
  const keys = subtreeKeys(key)
  return { repos: store.visibleRepos.filter((r) => r.issue_keys.some((k) => keys.has(k))), root: false }
})

/** Workspace livre não tem tarefa: os repositórios abrem num painel próprio, no mesmo lugar. */
const reposOpen = ref(false)

// --- Entrada e saída do painel da direita ---------------------------------------------------

/**
 * A mesma entrada da Sprint: o painel monta fora da vista e só entra quando a tarefa inteira
 * chegou (`ready`), para o título não chegar antes do selo e as contagens não pipocarem
 * depois. Se a resposta demorar demais, entra assim mesmo com o "Carregando…". Como aqui ele
 * empurra a tela, quem anima é a largura da coluna: a área encolhe junto com a entrada e, ao
 * fechar, faz o caminho de volta. Trocar de tarefa com ele aberto carrega no lugar, sem animar.
 */
const REVEAL_TIMEOUT = 1500
const drawerRevealed = ref(false)
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

const panelOpen = computed(() => (isIssue.value ? Boolean(selectedKey.value) && drawerRevealed.value : reposOpen.value))

screen.enter('workspace')

onMounted(async () => {
  await Promise.all([store.loadList(), localRepos.loaded ? null : localRepos.load()])
  if (!workspaceId.value && store.tabs.length) selectWorkspace(store.tabs[0].id)
})
onBeforeUnmount(() => screen.enter(null))

watch(
  workspaceId,
  (id) => {
    store.select(id)
    if (!id) return
    store.loadDetail(id)
    store.loadTree(id)
  },
  { immediate: true },
)

watch(selectedKey, (key) => screen.focusIssue(key), { immediate: true })
watch(
  () => store.tree,
  (tree) => screen.$patch({ visibleIssueKeys: tree ? tree.nodes.filter((n) => n.in_sprint).map((n) => n.key) : [] }),
)
watch(
  [selectedKey, () => store.tree],
  ([key]) => {
    if (key) store.markSeen(key)
  },
  { immediate: true },
)

// Sync, escrita no Jira ou "Recarregar": cards e repos se refazem. O painel da tarefa
// recarrega sozinho (ele também observa o `refresh.revision`).
watch(() => refresh.revision, () => {
  store.loadList()
  if (!workspaceId.value) return
  store.loadDetail()
  store.loadTree()
})

// Lembrete criado ou arquivado muda o ícone do rodapé dos cards.
watch(() => notes.revision, () => store.loadTree())

function patchQuery(patch) {
  router.replace({ query: { ...route.query, ...patch } })
}

function selectWorkspace(id) {
  router.replace({ query: { ws: id ? String(id) : undefined } })
}

function selectIssue(key) {
  patchQuery({ tarefa: key ?? undefined })
}

function selectRepo(slug) {
  // Lado a lado já mostra a linha do tempo: trocar de repo não tira o canvas da tela.
  patchQuery({ repo: slug, aba: view.value === 'lado' ? 'lado' : 'linha' })
}

async function closeTab(id) {
  await store.close(id)
  if (id === workspaceId.value) selectWorkspace(store.tabs[0]?.id ?? null)
}

async function openIssueWorkspace(key) {
  const ws = await store.openIssue(key)
  if (ws) selectWorkspace(ws.id)
}

async function openFreeWorkspace(title, repos) {
  const ws = await store.openFree(title, repos)
  if (ws) selectWorkspace(ws.id)
}

async function reopen(id) {
  await store.reopen(id)
  selectWorkspace(id)
}

function reload() {
  refresh.reload()
}

// --- Lado a lado: o canvas abre na largura de um card, e a divisão é arrastável -------------

/**
 * Pedido do dev: lado a lado é para olhar a linha do tempo com a tarefa à mão. O canvas abre
 * na largura de um card em foco — o card e a folga dos dois lados —, e todo o resto fica
 * para a linha do tempo. Arrastar alarga durante a visita; voltar ao lado a lado (ou o duplo
 * clique na divisão) traz a largura de um card de novo.
 */
const CARD_PANE = NODE_WIDTH + 72
const SPLIT_MIN = 240
// A linha do tempo nunca fica mais estreita que isto: abaixo, nem o painel de branches cabe.
const TIMELINE_MIN = 360
const SPLIT_STEP = 40

const tasksWidth = ref(CARD_PANE)
const areaEl = ref(null)
const areaWidth = ref(0)
let areaObserver = null

watch(areaEl, (el) => {
  areaObserver?.disconnect()
  if (!el || typeof ResizeObserver === 'undefined') return
  areaObserver = new ResizeObserver(() => (areaWidth.value = el.offsetWidth))
  areaObserver.observe(el)
})
onBeforeUnmount(() => areaObserver?.disconnect())

const splitMax = computed(() => (areaWidth.value ? Math.max(SPLIT_MIN, areaWidth.value - TIMELINE_MIN) : Infinity))
const clampSplit = (value) => Math.round(Math.min(splitMax.value, Math.max(SPLIT_MIN, value)))

function startSplit(event) {
  const area = areaEl.value
  if (!area) return
  const { left } = area.getBoundingClientRect()
  const move = (e) => (tasksWidth.value = clampSplit(e.clientX - left))
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
  }
  move(event)
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
}

function nudgeSplit(delta) {
  tasksWidth.value = clampSplit(tasksWidth.value + delta)
}

// --- Câmera do canvas ao trocar de área ------------------------------------------------------

/**
 * Sem tarefa aberta, lado a lado pousa na raiz: enquadrar a feature inteira na largura de um
 * card deixaria cada card do tamanho de um selo.
 */
const anchorKey = computed(() => (view.value === 'lado' ? rootKey.value : null))
const canvasEl = ref(null)

/**
 * Entrar no lado a lado traz a largura de um card e pousa a câmera no card em foco (o aberto
 * no painel, senão a raiz), no tamanho de foco. Espera dois quadros: o pane precisa ter
 * encolhido antes, senão a conta centraliza na largura velha. Trocar entre as outras áreas
 * não precisa disto — o canvas segue a tarefa em foco quando a largura muda (`SprintCanvas`).
 */
watch(view, async (value, previous) => {
  if (value !== 'lado' || previous === 'lado') return
  tasksWidth.value = CARD_PANE
  await nextTick()
  if (typeof requestAnimationFrame === 'function') {
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  }
  canvasEl.value?.focus?.(selectedKey.value ?? anchorKey.value)
})
</script>

<template>
  <div class="ws-page">
    <header class="ws-page__bar">
      <WorkspaceTabs :tabs="store.tabs" :current-id="workspaceId" @select="selectWorkspace" @close="closeTab" @new="selectWorkspace(null)" />
      <button type="button" class="btn btn--secondary ws-page__reload" title="Recarregar cards, repositórios e linha do tempo" @click="reload">
        <RefreshCw :size="14" :class="{ spin: store.treeLoading || store.detailLoading }" />
      </button>
    </header>

    <p v-if="store.actionError" class="ws-page__error" role="alert">{{ store.actionError }}</p>

    <WorkspaceStart
      v-if="!workspaceId"
      :closed="store.closed"
      :repos="localRepos.gitRepos"
      :opening="store.opening"
      :error="store.openError"
      @open-issue="openIssueWorkspace"
      @open-free="openFreeWorkspace"
      @reopen="reopen"
      @remove="store.remove"
    />

    <p v-else-if="store.listLoaded && !current" class="ws-page__empty">
      Workspace não encontrado.
      <button type="button" class="btn btn--secondary" @click="selectWorkspace(null)">Voltar</button>
    </p>

    <div v-else-if="current" class="ws-body">
      <section class="ws-main">
        <nav v-if="isIssue" class="ws-main__views" role="tablist" aria-label="Área principal">
          <button
            type="button"
            role="tab"
            class="ws-main__view"
            :class="{ 'ws-main__view--active': view === 'tarefas' }"
            :aria-selected="view === 'tarefas'"
            @click="chooseView('tarefas')"
          >
            <Workflow :size="14" /> Tarefas
            <span v-if="store.tree?.counters?.tasks" class="ws-main__count">{{ store.tree.counters.tasks }}</span>
          </button>
          <button
            type="button"
            role="tab"
            class="ws-main__view"
            :class="{ 'ws-main__view--active': view === 'linha' }"
            :aria-selected="view === 'linha'"
            @click="chooseView('linha')"
          >
            <GitGraph :size="14" /> Linha do tempo
          </button>
          <button
            type="button"
            role="tab"
            class="ws-main__view"
            :class="{ 'ws-main__view--active': view === 'lado' }"
            :aria-selected="view === 'lado'"
            title="Tarefas e linha do tempo juntas — arraste a divisão para ajustar"
            @click="chooseView('lado')"
          >
            <Columns2 :size="14" /> Lado a lado
          </button>
        </nav>
        <div v-else class="ws-main__views">
          <span class="ws-main__free">Workspace livre</span>
          <button
            type="button"
            class="ws-main__view"
            :class="{ 'ws-main__view--active': reposOpen }"
            :aria-pressed="reposOpen"
            title="Os repositórios deste workspace: adicionar, esconder, abrir no VS Code"
            @click="reposOpen = !reposOpen"
          >
            <FolderGit2 :size="14" /> Repositórios
            <span class="ws-main__count">{{ store.visibleRepos.length }}</span>
          </button>
        </div>

        <div ref="areaEl" class="ws-main__area card" :class="{ 'ws-main__area--split': view === 'lado' }">
          <!-- Na linha do tempo o canvas fica guardado (montado e invisível), não desmontado: a
               câmera continua onde estava, e voltar não recria nem remede cada card. -->
          <div
            v-if="isIssue"
            class="ws-main__pane ws-main__pane--tasks"
            :class="{ 'ws-main__pane--parked': view === 'linha' }"
            :style="view === 'lado' ? { flexBasis: `${tasksWidth}px` } : null"
            :inert="view === 'linha' || null"
          >
            <p v-if="store.treeError" class="ws-main__empty" role="alert">{{ store.treeError }}</p>
            <SprintCanvas
              v-else-if="store.tree?.nodes.length"
              ref="canvasEl"
              flow-id="workspace-tree"
              :tree="store.tree"
              :selected-key="selectedKey"
              :anchor-key="anchorKey"
              @select="selectIssue"
            />
            <p v-else-if="store.tree" class="ws-main__empty">Nenhuma tarefa no espelho para esta feature.</p>
            <p v-else class="ws-main__empty muted">Carregando cards…</p>
          </div>
          <div
            v-if="view === 'lado'"
            class="ws-main__splitter"
            role="separator"
            tabindex="0"
            aria-orientation="vertical"
            aria-label="Ajustar a largura das tarefas e da linha do tempo"
            :aria-valuenow="tasksWidth"
            :aria-valuemin="SPLIT_MIN"
            :aria-valuemax="Number.isFinite(splitMax) ? splitMax : undefined"
            title="Arraste para ajustar · duplo clique volta à largura de um card"
            @pointerdown.prevent="startSplit"
            @dblclick="tasksWidth = CARD_PANE"
            @keydown.left.prevent="nudgeSplit(-SPLIT_STEP)"
            @keydown.right.prevent="nudgeSplit(SPLIT_STEP)"
          />
          <div v-if="showTimeline" class="ws-main__pane ws-main__pane--timeline">
            <RepoTimeline
              :repos="localVisibleRepos"
              :repo="selectedRepo"
              :keys="featureKeys"
              :highlight-keys="highlightKeys"
              @select-repo="selectRepo"
              @open-issue="selectIssue"
            />
          </div>
        </div>

        <div
          v-if="!dock.collapsed"
          class="ws-main__resize"
          role="separator"
          aria-orientation="horizontal"
          aria-label="Ajustar a altura dos terminais"
          @pointerdown.prevent="startDockResize"
        />
        <TerminalDock
          class="ws-main__dock"
          :style="dock.collapsed ? null : { height: `${dock.height}px` }"
          :repos="localVisibleRepos"
          :all-repos="allLocalRepos"
          :selected-repo="selectedRepo"
          :collapsed="dock.collapsed"
          :workspace-id="workspaceId"
          :focus-repos="focusRepos"
          @toggle="dock.collapsed = !dock.collapsed"
          @pin-repo="store.pin($event, 'add')"
          @open-folder="store.openFolder"
        />
      </section>

      <!-- O painel é uma coluna da tela, não uma camada por cima: abrir empurra as abas, a
           área (tarefas, linha do tempo ou as duas) e os terminais, e nada fica escondido
           atrás dele. Desce do topo ao rodapé, como na Sprint. A coluna cresce do zero quando
           a tarefa chegou; ao fechar, o painel fica na tela enquanto ela encolhe. -->
      <div class="ws-panel" :class="{ 'ws-panel--open': panelOpen }">
        <Transition name="ws-panel">
          <IssueDrawer
            v-if="isIssue && selectedKey"
            class="ws-body__panel"
            :issue-key="selectedKey"
            @close="selectIssue(null)"
            @open="selectIssue"
            @ready="drawerRevealed = true"
          >
            <template #details>
              <InvolvedRepos
                v-if="drawerRepos"
                class="ws-body__repos"
                :repos="drawerRepos.repos"
                :hidden-repos="store.hiddenRepos"
                :addable="addable"
                :selected-repo="selectedRepo"
                :loading="store.detailLoading"
                :manage="drawerRepos.root"
                empty-text="Nenhum repositório com branch, PR ou título desta tarefa."
                @select-repo="selectRepo"
                @pin="store.pin"
                @open-folder="store.openFolder"
              >
                <button v-if="!drawerRepos.root" type="button" class="ws-body__all-repos" @click="selectIssue(rootKey)">
                  Todos os repositórios do workspace, na {{ rootKey }}
                </button>
              </InvolvedRepos>
            </template>
          </IssueDrawer>

          <aside v-else-if="!isIssue && reposOpen" class="ws-body__panel ws-free card" aria-label="Repositórios do workspace">
            <header class="ws-free__head">
              <div class="ws-free__titles">
                <p class="ws-free__type">WORKSPACE LIVRE</p>
                <h2 class="ws-free__title">{{ current.title }}</h2>
              </div>
              <button type="button" class="ws-free__close" title="Fechar" aria-label="Fechar painel" @click="reposOpen = false">
                <X :size="16" />
              </button>
            </header>
            <p class="ws-free__desc">Sem tarefa: só os repositórios que você escolheu, com linha do tempo e terminal.</p>
            <InvolvedRepos
              :repos="store.visibleRepos"
              :hidden-repos="store.hiddenRepos"
              :addable="addable"
              :selected-repo="selectedRepo"
              :loading="store.detailLoading"
              @select-repo="selectRepo"
              @pin="store.pin"
              @open-folder="store.openFolder"
            />
          </aside>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ws-page {
  height: 100%;
  min-height: 480px;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ws-page__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-width: 0;
}

.ws-page__reload {
  flex-shrink: 0;
  padding: 6px 10px;
}

.ws-page__error,
.ws-page__empty {
  margin: 0;
  font-size: var(--text-sm);
}

.ws-page__error {
  color: var(--color-error);
}

/* A área principal e o painel da direita lado a lado: o painel tem a altura toda. */
.ws-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.ws-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-main__views {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.ws-main__view {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
}

.ws-main__view--active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.ws-main__count {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
}

.ws-main__free {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.ws-main__area {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.ws-main__pane {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  position: relative;
}

.ws-main__area--split .ws-main__pane--tasks {
  flex: 0 0 auto;
}

/* Guardado: ocupa a área inteira por baixo (a largura não muda, nem a câmera), sem ser
   visto nem clicado. Não pode ser `display: none` — sem medida, o Vue Flow reclama e perde as
   dimensões do pane. E só `visibility: hidden` não basta: o Vue Flow põe `visibility:
   visible` e `pointer-events: all` em cada card, e os cards vazavam por cima da linha do
   tempo, clicáveis. Por isso a opacidade (que filho nenhum desfaz) e o `inert` no elemento,
   que tira clique e foco de tudo o que está dentro. */
.ws-main__pane--parked {
  position: absolute;
  inset: 0;
  visibility: hidden;
  opacity: 0;
  pointer-events: none;
}

.ws-main__splitter {
  flex-shrink: 0;
  width: 6px;
  margin: 0 -1px;
  border-inline: 1px solid var(--color-border);
  background: var(--color-surface-muted);
  cursor: col-resize;
  z-index: 1;
}

.ws-main__splitter:hover,
.ws-main__splitter:focus-visible {
  background: var(--color-primary-soft);
  outline: none;
}

.ws-main__resize {
  flex-shrink: 0;
  height: 6px;
  margin: -4px 0;
  border-radius: 3px;
  cursor: row-resize;
}

.ws-main__resize:hover {
  background: var(--color-primary-soft);
}

.ws-main__dock {
  flex-shrink: 0;
}

.ws-main__empty {
  margin: 0;
  padding: var(--space-5);
  font-size: var(--text-sm);
}

/* A coluna do painel. Fechada, tem largura zero e o painel (montado à espera da tarefa, ou
   saindo) fica para fora da borda direita, cortado. `clip` só na horizontal: o selo de
   status senta em cima do contorno, metade acima do painel, e não pode ser cortado. A largura
   é a do painel da tarefa nas outras telas, mais o respiro até a área principal. */
.ws-panel {
  --panel-width: max(360px, min(480px, 42vw));

  flex-shrink: 0;
  display: flex;
  width: 0;
  overflow-x: clip;
  transition: width 0.26s cubic-bezier(0.4, 0, 0.8, 0.4);
}

.ws-panel--open {
  width: calc(var(--panel-width) + var(--space-3));
  transition: width 0.34s cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* Duas classes: o painel da tarefa tem largura própria, e aqui ela vem da coluna. */
.ws-panel > .ws-body__panel {
  flex-shrink: 0;
  width: var(--panel-width);
  min-width: 0;
  min-height: 0;
  margin-left: var(--space-3);
}

/* Some enquanto a coluna encolhe: o mesmo tempo da saída na Sprint. */
.ws-panel-leave-active {
  transition: opacity 0.26s ease-in;
}

.ws-panel-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .ws-panel,
  .ws-panel--open,
  .ws-panel-leave-active {
    transition: none;
  }
}

.ws-body__repos {
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.ws-body__all-repos {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  font-size: var(--text-xs);
  color: var(--color-primary);
}

.ws-free {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  overflow-y: auto;
}

.ws-free__head {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}

.ws-free__titles {
  flex: 1;
  min-width: 0;
}

.ws-free__type {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
}

.ws-free__title {
  margin: 0;
  font-size: var(--text-lg);
  line-height: 24px;
}

.ws-free__close {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.ws-free__close:hover {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.ws-free__desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
