<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Columns2, GitGraph, RefreshCw, Workflow } from 'lucide-vue-next'

import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import SprintCanvas from '@/components/sprint/SprintCanvas.vue'
import RepoTimeline from '@/components/workspace/RepoTimeline.vue'
import TerminalDock from '@/components/workspace/TerminalDock.vue'
import WorkspaceSide from '@/components/workspace/WorkspaceSide.vue'
import WorkspaceStart from '@/components/workspace/WorkspaceStart.vue'
import WorkspaceTabs from '@/components/workspace/WorkspaceTabs.vue'
import { useIssueDetailStore } from '@/stores/issueDetail'
import { useNotesStore } from '@/stores/notes'
import { useRefreshStore } from '@/stores/refresh'
import { useScreenContextStore } from '@/stores/screenContext'
import { useWorkspaceStore } from '@/stores/workspace'
import { useWorkspaceReposStore } from '@/stores/workspaceRepos'

/**
 * Workspace (`/workspace?ws=<id>`): a feature numa aba. Estado na URL, como na Sprint —
 * `ws` é o workspace, `aba` a área principal (`tarefas` | `linha` | `lado`, as duas lado a
 * lado), `repo` o repositório da linha do tempo e `tarefa` o painel aberto.
 */
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const localRepos = useWorkspaceReposStore()
const issueDetail = useIssueDetailStore()
const refresh = useRefreshStore()
const notes = useNotesStore()
const screen = useScreenContextStore()

const workspaceId = computed(() => Number(route.query.ws) || null)
const selectedKey = computed(() => route.query.tarefa ?? null)
const current = computed(() => (workspaceId.value ? store.list.find((w) => w.id === workspaceId.value) ?? null : null))
const isIssue = computed(() => current.value?.kind === 'issue')
const VIEWS = ['tarefas', 'linha', 'lado']
const view = computed(() => {
  if (!isIssue.value) return 'linha'
  return VIEWS.includes(route.query.aba) ? route.query.aba : 'tarefas'
})
const showTasks = computed(() => view.value !== 'linha')
const showTimeline = computed(() => view.value !== 'tarefas')

const rootIssue = computed(() => {
  const key = current.value?.root_issue_key
  return key ? issueDetail.issues[key]?.data ?? null : null
})
const rootNode = computed(() => store.tree?.nodes.find((n) => n.key === current.value?.root_issue_key) ?? null)

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

watch(
  () => current.value?.root_issue_key,
  (key) => {
    if (key) issueDetail.load(key)
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

// Sync, escrita no Jira ou "Recarregar": cards, repos e a tarefa raiz se refazem.
watch(() => refresh.revision, () => {
  store.loadList()
  if (!workspaceId.value) return
  store.loadDetail()
  store.loadTree()
  if (current.value?.root_issue_key) issueDetail.load(current.value.root_issue_key)
  if (selectedKey.value) issueDetail.load(selectedKey.value)
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

// --- Painel da tarefa por cima da área principal --------------------------------------

const drawerEl = ref(null)
const drawerWidth = ref(0)
let drawerObserver = null

watch(drawerEl, (el) => {
  drawerObserver?.disconnect()
  drawerWidth.value = 0
  const node = el?.$el ?? el
  if (!node || typeof ResizeObserver === 'undefined') return
  drawerObserver = new ResizeObserver(() => (drawerWidth.value = node.offsetWidth + 24))
  drawerObserver.observe(node)
})
onBeforeUnmount(() => drawerObserver?.disconnect())

// --- Lado a lado: a divisão é arrastável e fica salva neste navegador ---------------------

const SPLIT_KEY = 'sprintai.workspace.split'
const SPLIT_MIN = 0.2
const SPLIT_MAX = 0.8

function readSplit() {
  try {
    const saved = Number(localStorage.getItem(SPLIT_KEY))
    if (saved >= SPLIT_MIN && saved <= SPLIT_MAX) return saved
  } catch {
    // Sem localStorage: metade e metade.
  }
  return 0.5
}

const split = ref(readSplit())
watch(split, (value) => {
  try {
    localStorage.setItem(SPLIT_KEY, String(value))
  } catch {
    // idem
  }
})

// Arredonda: somar 0,05 três vezes dá 0,6000000000000001, e isso ia para o localStorage.
const clampSplit = (value) => Math.round(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value)) * 1000) / 1000
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

function startSplit(event) {
  const area = areaEl.value
  if (!area) return
  const { left, width } = area.getBoundingClientRect()
  const move = (e) => (split.value = clampSplit((e.clientX - left) / width))
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
  }
  move(event)
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop)
}

function nudgeSplit(delta) {
  split.value = clampSplit(split.value + delta)
}

/**
 * Quanto o painel da tarefa cobre do canvas. Sozinho, o canvas fica embaixo do painel
 * inteiro; lado a lado, o painel cai primeiro sobre a linha do tempo, e só o que sobra dele
 * chega ao canvas.
 */
const rightInset = computed(() => {
  if (!drawerWidth.value) return 0
  if (view.value !== 'lado') return drawerWidth.value
  return Math.max(0, drawerWidth.value - areaWidth.value * (1 - split.value))
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
      <WorkspaceSide
        class="ws-body__side"
        :workspace="current"
        :issue="rootIssue"
        :root-node="rootNode"
        :repos="store.visibleRepos"
        :hidden-repos="store.hiddenRepos"
        :addable="addable"
        :selected-repo="selectedRepo"
        :loading="store.detailLoading"
        @select-repo="selectRepo"
        @pin="store.pin"
        @open-folder="store.openFolder"
        @open-issue="selectIssue"
      />

      <section class="ws-main">
        <nav v-if="isIssue" class="ws-main__views" role="tablist" aria-label="Área principal">
          <button
            type="button"
            role="tab"
            class="ws-main__view"
            :class="{ 'ws-main__view--active': view === 'tarefas' }"
            :aria-selected="view === 'tarefas'"
            @click="patchQuery({ aba: 'tarefas' })"
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
            @click="patchQuery({ aba: 'linha' })"
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
            @click="patchQuery({ aba: 'lado' })"
          >
            <Columns2 :size="14" /> Lado a lado
          </button>
        </nav>

        <div ref="areaEl" class="ws-main__area card" :class="{ 'ws-main__area--split': view === 'lado' }">
          <div
            v-if="showTasks"
            class="ws-main__pane ws-main__pane--tasks"
            :style="view === 'lado' ? { flexBasis: `${split * 100}%` } : null"
          >
            <p v-if="store.treeError" class="ws-main__empty" role="alert">{{ store.treeError }}</p>
            <SprintCanvas
              v-else-if="store.tree?.nodes.length"
              flow-id="workspace-tree"
              :tree="store.tree"
              :selected-key="selectedKey"
              :right-inset="rightInset"
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
            :aria-valuenow="Math.round(split * 100)"
            aria-valuemin="20"
            aria-valuemax="80"
            title="Arraste para ajustar · duplo clique volta ao meio"
            @pointerdown.prevent="startSplit"
            @dblclick="split = 0.5"
            @keydown.left.prevent="nudgeSplit(-0.05)"
            @keydown.right.prevent="nudgeSplit(0.05)"
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

          <IssueDrawer
            v-if="selectedKey"
            ref="drawerEl"
            class="ws-main__drawer"
            :issue-key="selectedKey"
            @close="selectIssue(null)"
            @open="selectIssue"
          />
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

.ws-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  gap: var(--space-3);
}

.ws-body__side {
  min-height: 0;
}

.ws-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.ws-main__views {
  display: flex;
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

/* O painel da tarefa flutua à direita da área, como na Sprint. */
.ws-main__drawer {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  bottom: var(--space-3);
  z-index: 5;
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 900px) {
  .ws-body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(360px, 1fr);
  }
}
</style>
