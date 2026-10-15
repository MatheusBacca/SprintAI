<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { GitBranch } from 'lucide-vue-next'
import TopbarTip from './TopbarTip.vue'
import { useIssueNavigation } from '@/composables/useIssueNavigation'
import { useRefreshStore } from '@/stores/refresh'
import { ALL_PROJECTS, useRepoIssuesStore } from '@/stores/repoIssues'
import { useShortcutsStore } from '@/stores/shortcuts'
import { ariaShortcut } from '@/utils/shortcuts'

/**
 * "WAIs por repositório": escolhe o repo à esquerda e vê as tarefas dele à direita, só da
 * sprint atual e das vizinhas (a próxima em cima, a anterior embaixo), cada linha na cor da
 * etapa do status (Configurações › Fluxo de trabalho › Progresso) — a mesma cor do card no
 * canvas. Em cima, um segmento por projeto do Bitbucket (o agrupamento com que os repos foram
 * escolhidos no sync), como as abas fixas de projeto do Workspace.
 */
const LABEL = 'WAIs por repositório'
const POSITIONS = { proxima: 'próxima', atual: 'atual', anterior: 'anterior' }
// Status que ninguém mapeou para uma etapa fica no cinza da borda, como no canvas.
const NO_STAGE = 'var(--color-border-strong)'

const store = useRepoIssuesStore()
const refresh = useRefreshStore()
const shortcuts = useShortcutsStore()
const { openIssueInSprint } = useIssueNavigation()
const root = ref(null)

// Aberto, o painel segue o espelho como as telas; fechado, a próxima abertura relê.
watch(
  () => refresh.revision,
  () => {
    if (store.open) store.load()
  },
)

/** Em "Todos", o nome do projeto abre o grupo de repos dele na lista da esquerda. */
function startsGroup(index) {
  if (store.activeProject !== ALL_PROJECTS) return false
  const repos = store.visibleRepos
  return index === 0 || repos[index].project_key !== repos[index - 1].project_key
}

/** Leva ao canvas da sprint da tarefa, com o card em foco — o destino das notificações. */
function openIssue(issue, sprint) {
  openIssueInSprint(issue.key, sprint.id)
  store.closePanel()
}

/** Clique fora fecha: o painel fica ancorado no botão, não é um modal com scrim. */
function onDocumentPointerDown(event) {
  if (store.open && root.value && !root.value.contains(event.target)) store.closePanel()
}

function onKeydown(event) {
  if (event.key === 'Escape' && store.open) {
    store.closePanel()
    event.stopPropagation()
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="repos">
    <TopbarTip :lines="[{ label: LABEL, combo: shortcuts.bindings.open_repo_issues }]">
      <button
        type="button"
        class="repos__toggle"
        :aria-label="LABEL"
        :aria-expanded="store.open"
        :aria-keyshortcuts="ariaShortcut(shortcuts.bindings.open_repo_issues)"
        @click="store.togglePanel()"
      >
        <GitBranch :size="16" />
      </button>
    </TopbarTip>

    <section v-if="store.open" class="repos__panel" :aria-label="LABEL">
      <header class="repos__head">
        <strong>{{ LABEL }}</strong>
        <span class="repos__window">sprint anterior, atual e próxima</span>
        <span v-if="store.loading && store.loaded" class="repos__loading">Atualizando…</span>
      </header>

      <p v-if="store.error && !store.repos.length" class="repos__empty repos__empty--error" role="alert">
        {{ store.error }}
      </p>
      <p v-else-if="!store.loaded" class="repos__empty">Carregando…</p>
      <p v-else-if="!store.repos.length" class="repos__empty">
        Nenhuma tarefa da sprint anterior, da atual ou da próxima ligada a um repositório. O vínculo
        sai da branch com a chave, do PR no Bitbucket ou do <code>[repo]</code> no começo do título.
      </p>

      <div v-else-if="store.projects.length > 1" class="repos__segments" role="group" aria-label="Projetos do Bitbucket">
        <button
          type="button"
          class="repos__segment"
          :class="{ 'repos__segment--on': store.activeProject === ALL_PROJECTS }"
          :aria-pressed="store.activeProject === ALL_PROJECTS"
          @click="store.selectProject(ALL_PROJECTS)"
        >
          Todos
        </button>
        <button
          v-for="project in store.projects"
          :key="project.key"
          type="button"
          class="repos__segment"
          :class="{ 'repos__segment--on': store.activeProject === project.key }"
          :aria-pressed="store.activeProject === project.key"
          :data-project="project.key"
          @click="store.selectProject(project.key)"
        >
          {{ project.name }} <span class="repos__segment-count">{{ project.count }}</span>
        </button>
      </div>

      <div v-if="store.loaded && store.repos.length" class="repos__body">
        <ul class="repos__list" aria-label="Repositórios">
          <li v-for="(repo, index) in store.visibleRepos" :key="repo.slug">
            <p v-if="startsGroup(index)" class="repos__group">{{ repo.project_name ?? 'Outros' }}</p>
            <button
              type="button"
              class="repos__repo"
              :class="{ 'repos__repo--on': repo.slug === store.current?.slug }"
              :aria-pressed="repo.slug === store.current?.slug"
              :data-slug="repo.slug"
              :style="{ '--repo': repo.color ?? NO_STAGE }"
              @click="store.select(repo.slug)"
            >
              <span class="repos__dot" aria-hidden="true" />
              <span class="repos__slug">{{ repo.slug }}</span>
              <span class="repos__count">{{ repo.issue_count }}</span>
            </button>
          </li>
        </ul>

        <div class="repos__sprints" :aria-label="`WAIs de ${store.current.slug}`">
          <section
            v-for="sprint in store.current.sprints"
            :key="sprint.id"
            class="repos__sprint"
            :data-sprint="sprint.id"
          >
            <h3 class="repos__sprint-name">
              <span class="repos__sprint-text">{{ sprint.name }}</span>
              <span class="repos__badge" :class="{ 'repos__badge--active': sprint.position === 'atual' }">
                {{ POSITIONS[sprint.position] }}
              </span>
              <span class="repos__sprint-count">{{ sprint.issues.length }}</span>
            </h3>
            <ul class="repos__issues">
              <li v-for="issue in sprint.issues" :key="issue.key">
                <button
                  type="button"
                  class="repos__issue"
                  :data-key="issue.key"
                  :style="{ '--tone': issue.stage?.color ?? NO_STAGE }"
                  :title="`${issue.key} — ${issue.summary}`"
                  @click="openIssue(issue, sprint)"
                >
                  <span class="repos__key">{{ issue.key }}</span>
                  <span class="repos__summary">{{ issue.summary }}</span>
                  <span class="repos__status">{{ issue.status }}</span>
                </button>
              </li>
            </ul>
          </section>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.repos {
  position: relative;
  flex-shrink: 0;
}

.repos__toggle {
  display: grid;
  place-items: center;
  width: var(--topbar-control-height);
  height: var(--topbar-control-height);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
}

.repos__toggle:hover,
.repos__toggle[aria-expanded='true'] {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.repos__panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: var(--z-drawer);
  display: flex;
  flex-direction: column;
  width: min(680px, calc(100vw - 32px));
  max-height: min(72vh, 600px);
  padding: var(--space-3);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.repos__head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  font-size: var(--text-sm);
}

.repos__window {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.repos__loading {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.repos__empty {
  margin: 0;
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.repos__empty--error {
  color: var(--color-error);
}

/* Repos e tarefas rolam cada um no seu canto: escolher outro repo não perde a lista dele. */
/* Os projetos do Bitbucket: a mesma pré-seleção das abas fixas do Workspace. */
.repos__segments {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: var(--space-3);
}

.repos__segment {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.repos__segment:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.repos__segment--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.repos__segment-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

.repos__group {
  margin: var(--space-2) 0 2px;
  padding: 0 8px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.repos__list li:first-child .repos__group {
  margin-top: 0;
}

.repos__body {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: var(--space-3);
  min-height: 0;
}

.repos__list,
.repos__issues {
  margin: 0;
  padding: 0;
  list-style: none;
}

.repos__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow: auto;
  padding-right: var(--space-2);
  border-right: 1px solid var(--color-border);
}

.repos__repo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  text-align: left;
}

.repos__repo:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.repos__repo--on {
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 600;
}

.repos__dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--repo);
}

.repos__slug {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.repos__count {
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
}

.repos__sprints {
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.repos__sprint + .repos__sprint {
  margin-top: var(--space-3);
}

/* Fica no topo enquanto as tarefas daquela sprint rolam por baixo. */
.repos__sprint-name {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 6px;
  padding: 2px 0 4px;
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
}

.repos__sprint-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.repos__badge {
  flex-shrink: 0;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-neutral-surface);
  color: var(--color-neutral-text);
  font-size: 10px;
  letter-spacing: 0;
  text-transform: none;
}

.repos__badge--active {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.repos__sprint-count {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
}

.repos__issues {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* A linha leva a cor da etapa do status: fundo esfumaçado na força dos cards do canvas
   (muda com o tema) e a faixa cheia à esquerda. */
.repos__issue {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: 6px 10px;
  border: 1px solid color-mix(in srgb, var(--tone) 40%, transparent);
  border-left: 4px solid var(--tone);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--tone) var(--card-tint-mix), var(--color-surface));
  font-size: var(--text-xs);
  color: var(--color-text);
  text-align: left;
}

.repos__issue:hover {
  border-color: var(--tone);
  background: color-mix(in srgb, var(--tone) calc(var(--card-tint-mix) + 12%), var(--color-surface));
}

.repos__key {
  font-family: var(--font-mono);
  font-weight: 700;
}

.repos__summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.repos__status {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: color-mix(in srgb, var(--tone) var(--card-tint-ink), var(--color-text));
}

@media (max-width: 640px) {
  .repos__body {
    grid-template-columns: 1fr;
  }

  .repos__list {
    flex-direction: row;
    overflow-x: auto;
    padding: 0 0 var(--space-2);
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }

  .repos__repo {
    white-space: nowrap;
  }

  .repos__status {
    display: none;
  }
}
</style>
