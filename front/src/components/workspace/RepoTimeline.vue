<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CloudDownload, FolderGit2, GitBranch, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, X } from 'lucide-vue-next'
import BranchesPanel from './BranchesPanel.vue'
import CommitDetail from './CommitDetail.vue'
import CommitGraph from './CommitGraph.vue'
import { useRepoTimelineStore } from '@/stores/repoTimeline'
import { formatRelative } from '@/utils/time'

/**
 * Aba "Linha do tempo" do Workspace: o grafo de commits de um repo envolvido.
 * **Só da feature** mostra a base e as branches com a chave das tarefas do workspace;
 * **Todas** é o `--all` do gitk (sem o stash).
 *
 * Atualiza sozinha: a cada poucos segundos, com a aba do navegador à vista, pergunta ao
 * back se o `.git` mudou — um commit feito no terminal aparece aqui em seguida.
 *
 * À esquerda, o painel de branches (locais, `origin/` e tags), com avançar e apagar branch
 * local. A busca do cabeçalho filtra o painel na hora e procura commits no histórico inteiro.
 * O botão de fetch é o `git fetch origin --prune` — o único jeito de trazer o Bitbucket.
 */
const props = defineProps({
  repos: { type: Array, required: true },
  repo: { type: String, default: null },
  keys: { type: Array, default: () => [] },
  highlightKeys: { type: Array, default: () => [] },
})
const emit = defineEmits(['select-repo', 'open-issue'])

const POLL_MS = 5000

const store = useRepoTimelineStore()

// Workspace livre não tem chave: "só da feature" vira a branch aberta no clone.
const scope = computed({
  get: () => store.scope,
  set: (value) => store.load(props.repo, { scope: value, keys: props.keys }),
})

watch(
  () => [props.repo, props.keys.join(',')],
  async ([repo], previous) => {
    await store.load(props.repo, { keys: props.keys })
    if (!previous || repo !== previous[0] || !store.panel.loaded) store.loadRefs()
  },
  { immediate: true },
)

// --- Busca --------------------------------------------------------------------------------

const SEARCH_DELAY_MS = 300
let searchTimer = null
const query = computed({
  get: () => store.query,
  set: (value) => {
    store.query = value
    clearTimeout(searchTimer)
    searchTimer = setTimeout(() => store.search(value), SEARCH_DELAY_MS)
  },
})
onBeforeUnmount(() => clearTimeout(searchTimer))

function clearSearch() {
  query.value = ''
}

const matchShas = computed(() =>
  store.query.trim().length >= 2 ? (store.searchResults?.commits ?? []).map((c) => c.sha) : [],
)

// --- Painel de branches: aberto ou fechado é conveniência deste navegador ----------------

const PANEL_KEY = 'sprintai.timeline.branches'
function readPanel() {
  try {
    return localStorage.getItem(PANEL_KEY) !== '0'
  } catch {
    return true
  }
}
const panelOpen = ref(readPanel())
watch(panelOpen, (open) => {
  try {
    localStorage.setItem(PANEL_KEY, open ? '1' : '0')
  } catch {
    // Sem localStorage: fica aberto no próximo carregamento.
  }
})

let timer = null
function tick() {
  if (typeof document !== 'undefined' && document.hidden) return
  store.poll()
}
onMounted(() => {
  timer = setInterval(tick, POLL_MS)
})
onBeforeUnmount(() => clearInterval(timer))

const graph = computed(() => store.graph)
const otherWorktrees = computed(() => store.worktrees.filter((w) => !w.is_main))

function worktreeHint(wt) {
  if (wt.outside_roots) return 'fora de C:\\projects — só aparece no grafo'
  if (wt.prunable) return 'a pasta sumiu'
  return wt.path
}
</script>

<template>
  <div class="timeline">
    <header class="timeline__bar">
      <button
        type="button"
        class="timeline__panel-toggle"
        :class="{ 'timeline__panel-toggle--on': panelOpen }"
        :title="panelOpen ? 'Esconder o painel de branches' : 'Mostrar o painel de branches'"
        :aria-expanded="panelOpen"
        @click="panelOpen = !panelOpen"
      >
        <PanelLeftClose v-if="panelOpen" :size="14" />
        <PanelLeftOpen v-else :size="14" />
        Branches
      </button>
      <div class="timeline__repos" role="tablist" aria-label="Repositório">
        <button
          v-for="r in repos"
          :key="r.slug"
          type="button"
          role="tab"
          class="timeline__repo"
          :class="{ 'timeline__repo--active': r.slug === repo }"
          :aria-selected="r.slug === repo"
          @click="emit('select-repo', r.slug)"
        >
          {{ r.slug }}
        </button>
      </div>

      <div class="segmented timeline__scope" role="radiogroup" aria-label="Quais branches">
        <label
          class="segmented__option"
          :class="{ 'segmented__option--on': scope === 'feature' }"
          :title="keys.length ? 'Só o que as branches da tarefa carregam, desde o ponto da base de onde saíram (sem branch, os commits que citam a chave)' : 'A branch aberta no clone'"
        >
          <input v-model="scope" type="radio" value="feature">
          {{ keys.length ? 'Só da feature' : 'Branch aberta' }}
        </label>
        <label class="segmented__option" :class="{ 'segmented__option--on': scope === 'all' }">
          <input v-model="scope" type="radio" value="all">
          Todas
        </label>
      </div>

      <label class="timeline__search">
        <Search :size="13" />
        <input v-model="query" type="search" placeholder="Buscar commit, branch, tag, autor ou hash…" aria-label="Buscar na linha do tempo">
        <button v-if="query" type="button" class="timeline__clear" aria-label="Limpar a busca" @click="clearSearch"><X :size="12" /></button>
      </label>

      <span v-if="graph" class="timeline__meta">
        <GitBranch :size="12" /> base <strong>{{ graph.base_branch ?? '?' }}</strong>
        · {{ graph.fetched_at ? `fetch ${formatRelative(graph.fetched_at)}` : 'sem fetch' }}
      </span>
      <button
        type="button"
        class="timeline__fetch"
        :disabled="!repo || store.fetching"
        title="git fetch origin --prune — traz do Bitbucket o que mudou e apaga as origin/ que sumiram lá. Não escreve nada no Bitbucket."
        @click="store.fetchRemote()"
      >
        <CloudDownload :size="13" :class="{ pulse: store.fetching }" />
        {{ store.fetching ? 'Buscando…' : 'Fetch' }}
      </button>
      <button
        type="button"
        class="timeline__reload"
        title="Ler o git de novo"
        aria-label="Ler o git de novo"
        :disabled="!repo || store.loading"
        @click="store.load(repo)"
      >
        <RefreshCw :size="13" :class="{ spin: store.loading }" />
      </button>
    </header>

    <ul v-if="otherWorktrees.length" class="timeline__worktrees" aria-label="Worktrees">
      <li
        v-for="wt in otherWorktrees"
        :key="wt.path"
        class="worktree"
        :class="{ 'worktree--outside': wt.outside_roots || wt.prunable }"
        :title="worktreeHint(wt)"
      >
        <FolderGit2 :size="12" />
        <span class="worktree__branch">{{ wt.branch ?? `HEAD ${wt.head?.slice(0, 7) ?? '?'}` }}</span>
        <span v-if="wt.outside_roots" class="worktree__flag">fora de C:\projects</span>
        <span v-else-if="wt.prunable" class="worktree__flag">pasta sumiu</span>
      </li>
    </ul>

    <p v-if="!repos.length" class="timeline__empty">
      Nenhum repositório com clone local neste workspace. Adicione um em Repositórios envolvidos — no painel da tarefa raiz ou, no workspace livre, no botão Repositórios.
    </p>
    <p v-else-if="store.error && !graph" class="timeline__empty" role="alert">{{ store.error }}</p>
    <p v-else-if="!graph" class="timeline__empty muted">Lendo o git…</p>
    <p v-else-if="!store.commits.length" class="timeline__empty">Nenhum commit nessas branches.</p>

    <div v-else class="timeline__body">
      <BranchesPanel
        v-if="panelOpen"
        :selected-sha="store.selectedSha"
        :base-branch="graph.base_branch"
        @open-issue="emit('open-issue', $event)"
      />
      <CommitGraph
        :key="`${repo}:${store.scope}`"
        class="timeline__graph"
        :commits="store.commits"
        :refs="store.refs"
        :worktrees="store.worktrees"
        :selected-sha="store.selectedSha"
        :highlight-keys="highlightKeys"
        :has-more="store.hasMore"
        :loading-more="store.loadingMore"
        :issue-status="store.issueStatus"
        :match-shas="matchShas"
        :scroll-to="store.scrollTo"
        @select="store.selectCommit"
        @open-issue="emit('open-issue', $event)"
        @load-more="store.loadMore"
      />
      <CommitDetail
        v-if="store.selectedSha"
        :sha="store.selectedSha"
        :detail="store.detail"
        :loading="store.detailLoading"
        :error="store.detailError"
        :issue-status="store.issueStatus"
        @close="store.selectCommit(null)"
        @select="store.selectCommit"
        @open-issue="emit('open-issue', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.timeline__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.timeline__repos {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.timeline__repo {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
}

.timeline__repo--active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.segmented {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
}

.segmented__option {
  position: relative;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.segmented__option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.segmented__option--on {
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  color: var(--color-primary);
  font-weight: 600;
}

.segmented__option:has(input:focus-visible) {
  outline: 2px solid var(--color-primary-focus-ring);
}

.timeline__meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.timeline__search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 1 1 220px;
  max-width: 340px;
  padding: 4px 8px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-muted);
}

.timeline__search:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.timeline__search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: none;
  color: var(--color-text);
  font: inherit;
  font-size: var(--text-xs);
}

.timeline__clear {
  display: grid;
  place-items: center;
  border: 0;
  background: none;
  color: var(--color-text-muted);
}

.timeline__fetch {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
}

.timeline__fetch:not(:disabled):hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.timeline__panel-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 500;
}

.timeline__panel-toggle--on {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.pulse {
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}

.timeline__reload {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
}

.timeline__worktrees {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  list-style: none;
  border-bottom: 1px solid var(--color-border);
}

.worktree {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.worktree__branch {
  font-family: var(--font-mono);
}

.worktree--outside {
  border-style: dashed;
  color: var(--color-text-muted);
}

.worktree__flag {
  color: var(--color-warning-text);
}

.timeline__empty {
  margin: 0;
  padding: var(--space-5);
  font-size: var(--text-sm);
}

.timeline__body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.timeline__graph {
  flex: 1;
  min-width: 0;
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
