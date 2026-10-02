<script setup>
import { computed, ref } from 'vue'
import { CodeXml, Eye, EyeOff, FolderGit2, GitBranch, Plus, SquareTerminal } from 'lucide-vue-next'
import StatusChip from '@/components/jira/StatusChip.vue'
import StoryPointsChip from '@/components/jira/StoryPointsChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { formatRelative } from '@/utils/time'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Coluna da esquerda do Workspace: a tarefa raiz (ou o nome do workspace livre) e os
 * repositórios envolvidos, cada um dizendo de onde veio. Clicar num repo escolhe o repo
 * da linha do tempo e do terminal.
 */
const props = defineProps({
  workspace: { type: Object, required: true },
  /** Detalhe da tarefa raiz (`GET /issues/{key}`); nulo no workspace livre. */
  issue: { type: Object, default: null },
  /** Nó da raiz na árvore — traz o título em pedaços, com o `[repo]` pintado. */
  rootNode: { type: Object, default: null },
  repos: { type: Array, default: () => [] },
  hiddenRepos: { type: Array, default: () => [] },
  /** Repos locais que ainda não estão na lista, para "adicionar". */
  addable: { type: Array, default: () => [] },
  selectedRepo: { type: String, default: null },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['select-repo', 'pin', 'open-folder', 'open-issue'])

const SOURCE_LABELS = { branch: 'branch local', pr: 'PR no Bitbucket', title: 'título', pin: 'fixado' }

const titleParts = computed(() => (props.rootNode?.title_parts?.length ? props.rootNode.title_parts : null))
const adding = ref('')
const showHidden = ref(false)

function add() {
  if (!adding.value) return
  emit('pin', adding.value, 'add')
  adding.value = ''
}

function sourcesText(repo) {
  return repo.sources.map((s) => SOURCE_LABELS[s] ?? s).join(' · ')
}
</script>

<template>
  <aside class="side card" aria-label="Tarefa e repositórios do workspace">
    <section class="side__issue">
      <template v-if="workspace.kind === 'issue'">
        <p class="side__type">
          <span>{{ (issue?.issue_type ?? workspace.issue_type ?? '').toUpperCase() }}</span>
          <a
            v-if="safeUrl(issue?.url)"
            :href="safeUrl(issue.url)"
            target="_blank"
            rel="noopener noreferrer"
            class="side__key"
            title="Abrir no Jira"
          >{{ workspace.root_issue_key }}</a>
          <button v-else type="button" class="side__key side__key--button" @click="emit('open-issue', workspace.root_issue_key)">
            {{ workspace.root_issue_key }}
          </button>
        </p>
        <h1 class="side__title">
          <template v-if="titleParts">
            <span v-for="(part, i) in titleParts" :key="i" :style="part.color ? { color: part.color } : null">{{ part.text }}</span>
          </template>
          <template v-else>{{ issue?.summary ?? workspace.title }}</template>
        </h1>
        <div v-if="issue" class="side__chips">
          <StatusChip class="side__status" :issue-key="issue.key" :status="issue.status" />
          <StoryPointsChip class="side__sp" :issue-key="issue.key" :points="issue.story_points" />
          <PrStatusBadge
            :status="issue.pull_requests.status"
            :pr-count="issue.pull_requests.pr_count"
            :build-failed="issue.pull_requests.build_failed"
            :links="issue.pull_requests.links ?? []"
            :issue-key="issue.key"
            :review="issue.pull_requests.review"
            size="sm"
          />
        </div>
        <p v-if="issue" class="side__dates">
          Atualizada {{ formatRelative(issue.updated_at) }}
          <template v-if="issue.assignee_name"> · {{ issue.assignee_name }}</template>
        </p>
        <p v-if="issue?.description_text" class="side__desc" :title="issue.description_text">{{ issue.description_text }}</p>
        <button type="button" class="side__more" @click="emit('open-issue', workspace.root_issue_key)">Ver a tarefa</button>
      </template>
      <template v-else>
        <p class="side__type">WORKSPACE LIVRE</p>
        <h1 class="side__title">{{ workspace.title }}</h1>
        <p class="side__desc">Sem tarefa: só os repositórios que você escolheu, com linha do tempo e terminal.</p>
      </template>
    </section>

    <section class="side__repos">
      <header class="side__head">
        <h2>Repositórios envolvidos</h2>
        <span class="side__count">{{ repos.length }}</span>
      </header>

      <p v-if="loading && !repos.length" class="side__muted">Procurando branches e PRs…</p>
      <p v-else-if="!repos.length" class="side__muted">
        Nenhum repositório achado pela branch, pelo PR ou pelo título. Adicione abaixo.
      </p>

      <ul class="repos">
        <li
          v-for="repo in repos"
          :key="repo.slug"
          class="repo"
          :class="{ 'repo--selected': repo.slug === selectedRepo, 'repo--remote': !repo.local }"
          :data-repo="repo.slug"
        >
          <button type="button" class="repo__main" :disabled="!repo.local" @click="emit('select-repo', repo.slug)">
            <FolderGit2 :size="15" class="repo__icon" />
            <span class="repo__text">
              <span class="repo__name">{{ repo.slug }}</span>
              <span class="repo__sources">{{ repo.local ? sourcesText(repo) : 'sem clone em C:\\projects' }}</span>
              <span v-for="branch in repo.branches.slice(0, 2)" :key="branch" class="repo__branch" :title="branch">
                <GitBranch :size="11" /> {{ branch }}
              </span>
            </span>
          </button>
          <div class="repo__actions">
            <button
              v-if="repo.local"
              type="button"
              class="repo__action"
              title="Abrir no VS Code"
              aria-label="Abrir no VS Code"
              @click="emit('open-folder', 'ide', repo.path)"
            >
              <CodeXml :size="14" />
            </button>
            <button
              v-if="repo.local"
              type="button"
              class="repo__action"
              title="Abrir no Windows Terminal"
              aria-label="Abrir no Windows Terminal"
              @click="emit('open-folder', 'terminal', repo.path)"
            >
              <SquareTerminal :size="14" />
            </button>
            <button
              type="button"
              class="repo__action"
              :title="repo.sources.length === 1 && repo.sources[0] === 'pin' ? 'Tirar do workspace' : 'Esconder deste workspace'"
              aria-label="Esconder"
              @click="emit('pin', repo.slug, repo.sources.length === 1 && repo.sources[0] === 'pin' ? 'auto' : 'hide')"
            >
              <EyeOff :size="14" />
            </button>
          </div>
        </li>
      </ul>

      <div v-if="addable.length" class="side__add">
        <select v-model="adding" class="field__input side__select" aria-label="Adicionar repositório">
          <option value="">Adicionar repositório…</option>
          <option v-for="slug in addable" :key="slug" :value="slug">{{ slug }}</option>
        </select>
        <button type="button" class="btn btn--secondary side__add-btn" :disabled="!adding" title="Fixar neste workspace" @click="add">
          <Plus :size="14" />
        </button>
      </div>

      <div v-if="hiddenRepos.length" class="side__hidden">
        <button type="button" class="side__toggle" @click="showHidden = !showHidden">
          {{ hiddenRepos.length }} escondido(s)
        </button>
        <ul v-if="showHidden" class="side__hidden-list">
          <li v-for="repo in hiddenRepos" :key="repo.slug">
            {{ repo.slug }}
            <button type="button" class="repo__action" title="Mostrar de novo" aria-label="Mostrar de novo" @click="emit('pin', repo.slug, 'auto')">
              <Eye :size="13" />
            </button>
          </li>
        </ul>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.side {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}

.side__issue {
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.side__type {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
}

.side__key {
  border: 0;
  padding: 0;
  background: none;
  font: inherit;
  color: var(--color-primary);
}

.side__key--button {
  cursor: pointer;
}

.side__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-lg);
  line-height: 24px;
}

.side__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.side__status,
.side__sp {
  padding: 2px 8px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.side__dates,
.side__muted {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.side__desc {
  display: -webkit-box;
  margin: var(--space-2) 0 0;
  overflow: hidden;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  white-space: pre-line;
}

.side__more {
  margin-top: var(--space-2);
  padding: 0;
  border: 0;
  background: none;
  font-size: var(--text-xs);
  color: var(--color-primary);
}

.side__repos {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
}

.side__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.side__head h2 {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
}

.side__count {
  padding: 0 8px;
  border-radius: 999px;
  background: var(--color-accent-surface);
  color: var(--color-accent-text);
  font-size: 11px;
  font-weight: 600;
}

.repos {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.repo {
  display: flex;
  align-items: flex-start;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.repo--selected {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.repo__main {
  flex: 1;
  min-width: 0;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 0;
  background: none;
  text-align: left;
  color: inherit;
}

.repo__main:disabled {
  cursor: default;
}

.repo__icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-primary);
}

.repo--remote .repo__icon {
  color: var(--color-text-muted);
}

.repo__text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.repo__name {
  font-size: var(--text-sm);
  font-weight: 600;
}

.repo__sources {
  font-size: 11px;
  color: var(--color-text-muted);
}

.repo__branch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.repo__actions {
  display: flex;
  gap: 2px;
  padding: 6px 6px 0 0;
}

.repo__action {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.repo__action:hover {
  background: var(--color-surface-hover);
  color: var(--color-primary);
}

.side__add {
  display: flex;
  gap: var(--space-2);
}

.side__select {
  padding: 6px 10px;
}

.side__add-btn {
  padding: 6px 10px;
}

.side__toggle {
  padding: 0;
  border: 0;
  background: none;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.side__hidden-list {
  margin: var(--space-1) 0 0;
  padding: 0;
  list-style: none;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.side__hidden-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
