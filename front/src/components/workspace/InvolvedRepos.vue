<script setup>
import { ref } from 'vue'
import { CodeXml, Eye, EyeOff, FolderGit2, GitBranch, Plus, SquareTerminal } from 'lucide-vue-next'

/**
 * Repositórios envolvidos: cada um diz de onde veio (branch, PR, título ou fixado). Clicar
 * num repo escolhe o repo da linha do tempo e do terminal. No Workspace mora na aba Detalhes
 * do painel da tarefa; no workspace livre, no painel de repositórios.
 *
 * `manage` liga o adicionar e os escondidos: só onde a lista é a do workspace inteiro (a
 * tarefa raiz, o workspace livre). Na tarefa filha a lista é recortada, e um repo fixado ali
 * sumiria da própria lista na hora.
 */
defineProps({
  repos: { type: Array, default: () => [] },
  hiddenRepos: { type: Array, default: () => [] },
  /** Repos locais que ainda não estão na lista, para "adicionar". */
  addable: { type: Array, default: () => [] },
  selectedRepo: { type: String, default: null },
  loading: { type: Boolean, default: false },
  manage: { type: Boolean, default: true },
  emptyText: { type: String, default: 'Nenhum repositório achado pela branch, pelo PR ou pelo título. Adicione abaixo.' },
})
const emit = defineEmits(['select-repo', 'pin', 'open-folder'])

const SOURCE_LABELS = { branch: 'branch local', pr: 'PR no Bitbucket', title: 'título', pin: 'fixado' }

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

const onlyPinned = (repo) => repo.sources.length === 1 && repo.sources[0] === 'pin'
</script>

<template>
  <section class="involved" aria-label="Repositórios envolvidos">
    <header class="involved__head">
      <h2><FolderGit2 :size="15" /> Repositórios envolvidos</h2>
      <span class="involved__count">{{ repos.length }}</span>
    </header>

    <p v-if="loading && !repos.length" class="involved__muted">Procurando branches e PRs…</p>
    <p v-else-if="!repos.length" class="involved__muted">{{ emptyText }}</p>

    <ul v-if="repos.length" class="repos">
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
            <!-- Mesma cor do colchete no título do card (Configurações › Cores dos cards). -->
            <span class="repo__name" :class="{ 'repo__name--painted': repo.color }" :style="repo.color ? { '--repo': repo.color } : undefined">
              {{ repo.slug }}
            </span>
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
            :title="onlyPinned(repo) ? 'Tirar do workspace' : 'Esconder deste workspace'"
            aria-label="Esconder"
            @click="emit('pin', repo.slug, onlyPinned(repo) ? 'auto' : 'hide')"
          >
            <EyeOff :size="14" />
          </button>
        </div>
      </li>
    </ul>

    <div v-if="manage && addable.length" class="involved__add">
      <select v-model="adding" class="field__input involved__select" aria-label="Adicionar repositório">
        <option value="">Adicionar repositório…</option>
        <option v-for="slug in addable" :key="slug" :value="slug">{{ slug }}</option>
      </select>
      <button type="button" class="btn btn--secondary involved__add-btn" :disabled="!adding" title="Fixar neste workspace" @click="add">
        <Plus :size="14" />
      </button>
    </div>

    <div v-if="manage && hiddenRepos.length" class="involved__hidden">
      <button type="button" class="involved__toggle" @click="showHidden = !showHidden">
        {{ hiddenRepos.length }} escondido(s)
      </button>
      <ul v-if="showHidden" class="involved__hidden-list">
        <li v-for="repo in hiddenRepos" :key="repo.slug">
          {{ repo.slug }}
          <button type="button" class="repo__action" title="Mostrar de novo" aria-label="Mostrar de novo" @click="emit('pin', repo.slug, 'auto')">
            <Eye :size="13" />
          </button>
        </li>
      </ul>
    </div>

    <slot />
  </section>
</template>

<style scoped>
.involved {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.involved__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.involved__head h2 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
}

.involved__count {
  padding: 0 8px;
  border-radius: 999px;
  background: var(--color-accent-surface);
  color: var(--color-accent-text);
  font-size: 11px;
  font-weight: 600;
}

.involved__muted {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
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

/* A mesma mistura do nome no título do card: a cor crua some no tema escuro. */
.repo__name--painted {
  color: color-mix(in srgb, var(--repo) var(--card-tint-ink), var(--color-text));
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

.involved__add {
  display: flex;
  gap: var(--space-2);
}

.involved__select {
  padding: 6px 10px;
}

.involved__add-btn {
  padding: 6px 10px;
}

.involved__toggle {
  padding: 0;
  border: 0;
  background: none;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.involved__hidden-list {
  margin: var(--space-1) 0 0;
  padding: 0;
  list-style: none;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.involved__hidden-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
