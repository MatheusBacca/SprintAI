<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/services/api'
import RepoPicker from './RepoPicker.vue'
import { useSyncStore } from '@/stores/sync'
import { formatRelative } from '@/utils/time'

const sync = useSyncStore()

// structuredClone não aceita o proxy reativo do Pinia; o escopo é JSON puro.
const clone = (value) => JSON.parse(JSON.stringify(value))

const draft = ref(null)
const boards = ref([])
const boardSprints = ref([])
const discoveryError = ref(null)

const STATUS_LABEL = { success: 'Sucesso', partial: 'Parcial', failed: 'Falhou', running: 'Em andamento' }
const STATE_LABEL = { active: 'Ativa', future: 'Futura', closed: 'Fechada' }

onMounted(async () => {
  await Promise.all([sync.loadScope(), sync.loadSprints(), sync.loadStatus()])
  draft.value = clone(sync.scope)
  await loadBoards()
})

watch(
  () => draft.value?.jira.board_ids[0],
  (boardId) => boardId && loadBoardSprints(boardId),
)

async function loadBoards() {
  discoveryError.value = null
  try {
    const keys = draft.value.jira.project_keys
    const lists = await Promise.all(keys.map((k) => api.get(`/jira/boards?project_key=${encodeURIComponent(k)}`)))
    boards.value = lists.flat().filter((b) => b.type === 'scrum')
  } catch (e) {
    discoveryError.value = e.message
  }
}

async function loadBoardSprints(boardId) {
  try {
    const result = await api.get(`/jira/boards/${boardId}/sprints?state=active,future,closed`)
    boardSprints.value = result.sprints
  } catch (e) {
    discoveryError.value = e.message
  }
}

const squads = computed(() => {
  const counts = new Map()
  for (const s of boardSprints.value) if (s.squad) counts.set(s.squad, (counts.get(s.squad) ?? 0) + 1)
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b, 'pt-BR'))
})

const buckets = computed(() =>
  boardSprints.value.filter((s) => !s.squad && s.state !== 'closed').map((s) => s.name),
)

const selectedBoard = computed({
  get: () => draft.value?.jira.board_ids[0] ?? null,
  set: (id) => (draft.value.jira.board_ids = id ? [Number(id)] : []),
})

function toggleSquad(squad) {
  const list = draft.value.jira.squads
  const i = list.findIndex((s) => s.toLowerCase() === squad.toLowerCase())
  i >= 0 ? list.splice(i, 1) : list.push(squad)
}

const dirty = computed(() => draft.value && JSON.stringify(draft.value) !== JSON.stringify(sync.scope))

// Sprints com muito volume merecem aviso (ex.: baldes de bugs com mil+ tarefas).
const HEAVY_SPRINT = 300
const scopeSummary = computed(() => {
  const total = sync.sprints.reduce((acc, s) => acc + s.issue_count, 0)
  const heavy = sync.sprints.filter((s) => s.issue_count >= HEAVY_SPRINT)
  return { total, heavy }
})

async function save() {
  if (await sync.saveScope(draft.value)) draft.value = clone(sync.scope)
}

function discard() {
  draft.value = clone(sync.scope)
}
</script>

<template>
  <div v-if="draft" class="sync-panel">
    <p v-if="discoveryError" class="sync-panel__error" role="alert">{{ discoveryError }}</p>

    <article class="card sync-card">
      <header>
        <h2 class="sync-card__title">Jira</h2>
        <p class="sync-card__desc">Quais sprints e tarefas entram no espelho local.</p>
      </header>

      <fieldset class="sync-card__fieldset">
        <legend class="field__label">Tarefas</legend>
        <div class="segmented" role="radiogroup">
          <label class="segmented__option" :class="{ 'segmented__option--on': draft.jira.assignee_scope === 'mine' }">
            <input v-model="draft.jira.assignee_scope" type="radio" value="mine">
            Só as minhas
          </label>
          <label class="segmented__option" :class="{ 'segmented__option--on': draft.jira.assignee_scope === 'all' }">
            <input v-model="draft.jira.assignee_scope" type="radio" value="all">
            Sprint inteira
          </label>
        </div>
        <span class="field__hint">
          {{ draft.jira.assignee_scope === 'mine'
            ? 'Tarefas em que você é o Responsável, mais os épicos/enhancements pais delas (para montar a árvore).'
            : 'Todas as tarefas das sprints do escopo, inclusive de outros devs.' }}
        </span>
      </fieldset>

      <div class="field-row">
        <label class="field">
          <span class="field__label">Board</span>
          <select v-model="selectedBoard" class="field__input">
            <option v-for="b in boards" :key="b.id" :value="b.id">{{ b.name }} ({{ b.project_key }} · {{ b.id }})</option>
            <option v-if="!boards.some((b) => b.id === selectedBoard)" :value="selectedBoard">Board {{ selectedBoard }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field__label">Sprints fechadas espelhadas</span>
          <input v-model.number="draft.jira.closed_sprints_limit" class="field__input" type="number" min="0" max="100">
          <span class="field__hint">As mais recentes; ficam congeladas depois da primeira carga.</span>
        </label>
      </div>

      <fieldset class="sync-card__fieldset">
        <legend class="field__label">Squads</legend>
        <div class="chips">
          <label v-for="[squad, count] in squads" :key="squad" class="chip" :class="{ 'chip--on': draft.jira.squads.some((s) => s.toLowerCase() === squad.toLowerCase()) }">
            <input type="checkbox" :checked="draft.jira.squads.some((s) => s.toLowerCase() === squad.toLowerCase())" @change="toggleSquad(squad)">
            {{ squad }} <small>{{ count }} sprints</small>
          </label>
        </div>
        <span class="field__hint">Nenhuma marcada = todas as squads.</span>
      </fieldset>

      <label class="toggle">
        <input v-model="draft.jira.include_unsquadded" type="checkbox">
        <span>
          Incluir baldes sem squad
          <span v-if="buckets.length" class="field__hint"> — {{ buckets.join(', ') }}</span>
        </span>
      </label>

      <label class="field sync-card__narrow">
        <span class="field__label">Minhas tarefas fora das sprints (dias)</span>
        <input v-model.number="draft.jira.my_issues_lookback_days" class="field__input" type="number" min="1" max="365">
        <span class="field__hint">Abertas + concluídas neste período; alimentam a visão Semana.</span>
      </label>
    </article>

    <article class="card sync-card">
      <header>
        <h2 class="sync-card__title">Repositórios do Bitbucket</h2>
        <p class="sync-card__desc">Só os repositórios marcados são sincronizados (PRs, aprovações, build e branches com a chave da tarefa).</p>
      </header>
      <fieldset class="sync-card__fieldset">
        <legend class="field__label">Pull requests</legend>
        <div class="segmented" role="radiogroup">
          <label class="segmented__option" :class="{ 'segmented__option--on': draft.bitbucket.pr_scope === 'mine' }">
            <input v-model="draft.bitbucket.pr_scope" type="radio" value="mine">
            Só os meus
          </label>
          <label class="segmented__option" :class="{ 'segmented__option--on': draft.bitbucket.pr_scope === 'all' }">
            <input v-model="draft.bitbucket.pr_scope" type="radio" value="all">
            Todos dos repositórios
          </label>
        </div>
        <span class="field__hint">
          {{ draft.bitbucket.pr_scope === 'mine'
            ? 'PRs em que você é autor ou revisor, ou ligados a tarefas suas.'
            : 'Todos os PRs dos repositórios marcados.' }}
        </span>
      </fieldset>
      <RepoPicker v-model="draft.bitbucket.repo_slugs" />
      <p v-if="!draft.bitbucket.repo_slugs.length" class="sync-panel__warn">
        Nenhum repositório marcado: o status de PR não vai aparecer nas tarefas.
      </p>
    </article>

    <article class="card sync-card">
      <header>
        <h2 class="sync-card__title">Agendamento</h2>
      </header>
      <div class="field-row">
        <label class="toggle">
          <input v-model="draft.enabled" type="checkbox">
          <span>Sincronizar automaticamente</span>
        </label>
        <label class="field">
          <span class="field__label">A cada (minutos)</span>
          <input v-model.number="draft.interval_minutes" class="field__input" type="number" min="1" max="240" :disabled="!draft.enabled">
        </label>
      </div>
    </article>

    <div class="sync-panel__actions">
      <p v-if="sync.scopeFeedback" class="conn__feedback" :data-type="sync.scopeFeedback.type" role="status">{{ sync.scopeFeedback.text }}</p>
      <button type="button" class="btn btn--secondary" :disabled="!dirty || sync.scopeSaving" @click="discard">Descartar</button>
      <button type="button" class="btn btn--primary" :disabled="!dirty || sync.scopeSaving" @click="save">
        {{ sync.scopeSaving ? 'Salvando…' : 'Salvar escopo' }}
      </button>
    </div>

    <article class="card sync-card">
      <header class="sync-card__header">
        <div>
          <h2 class="sync-card__title">Última sincronização</h2>
          <p v-if="sync.lastRun" class="sync-card__desc">
            {{ STATUS_LABEL[sync.lastRun.status] }} · {{ sync.lastRun.trigger === 'manual' ? 'manual' : 'agendada' }} ·
            {{ formatRelative(sync.lastRun.finished_at || sync.lastRun.started_at) }}
          </p>
          <p v-else class="sync-card__desc">Ainda não houve sincronização.</p>
        </div>
        <button type="button" class="btn btn--primary" :disabled="sync.running || sync.triggering || dirty" :title="dirty ? 'Salve o escopo antes' : undefined" @click="sync.trigger()">
          {{ sync.running ? 'Sincronizando…' : 'Sincronizar agora' }}
        </button>
      </header>

      <ul v-if="sync.lastRun?.errors?.length" class="sync-card__errors">
        <li v-for="(e, i) in sync.lastRun.errors" :key="i"><strong>{{ e.stage }}</strong>: {{ e.message }}</li>
      </ul>

      <dl v-if="sync.status" class="stats">
        <div><dt>Tarefas</dt><dd>{{ sync.status.counts.issues }}</dd></div>
        <div><dt>Sprints no escopo</dt><dd>{{ sync.status.counts.sprints_in_scope }}</dd></div>
        <div><dt>Comentários</dt><dd>{{ sync.status.counts.comments }}</dd></div>
        <div><dt>Repositórios</dt><dd>{{ sync.status.counts.repositories }}</dd></div>
        <div><dt>Pull requests</dt><dd>{{ sync.status.counts.pull_requests }}</dd></div>
        <div><dt>Branches</dt><dd>{{ sync.status.counts.branches }}</dd></div>
      </dl>

      <p v-if="scopeSummary.heavy.length" class="sync-panel__warn">
        {{ scopeSummary.heavy.map((s) => `${s.name} (${s.issue_count})`).join(', ') }} concentram a maior parte das
        {{ scopeSummary.total }} tarefas espelhadas. Se não precisar delas, desmarque "Incluir baldes sem squad"
        <template v-if="draft.jira.assignee_scope === 'all'"> ou volte para "Só as minhas"</template>.
      </p>

      <table v-if="sync.sprints.length" class="sprints">
        <thead><tr><th>Sprint</th><th>Estado</th><th>Squad</th><th class="num">Tarefas</th></tr></thead>
        <tbody>
          <tr v-for="s in sync.sprints" :key="s.id">
            <td>{{ s.name }}</td>
            <td>{{ STATE_LABEL[s.state] }}</td>
            <td>{{ s.squad ?? '—' }}</td>
            <td class="num">{{ s.issue_count }}</td>
          </tr>
        </tbody>
      </table>
    </article>
  </div>
  <p v-else class="muted">Carregando escopo…</p>
</template>

<style scoped>
.sync-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.sync-card {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.sync-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}

.sync-card__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.sync-card__desc {
  margin: var(--space-1) 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.sync-card__fieldset {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sync-card__narrow {
  max-width: 320px;
}

.sync-card__errors {
  margin: 0;
  padding: var(--space-3) var(--space-3) var(--space-3) var(--space-6);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
}

.chip small {
  color: var(--color-text-muted);
}

.chip--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.segmented {
  display: inline-flex;
  width: fit-content;
  padding: 2px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
}

.segmented__option {
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
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

.toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  cursor: pointer;
}

.sync-panel__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.sync-panel__actions .conn__feedback {
  margin: 0 auto 0 0;
}

.conn__feedback {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.conn__feedback[data-type='success'] {
  background: var(--color-success-surface-soft);
  color: var(--color-success);
}

.conn__feedback[data-type='error'] {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.sync-panel__error,
.sync-panel__warn {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.sync-panel__error {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.sync-panel__warn {
  background: var(--color-warning-surface-soft);
  color: var(--color-warning-text);
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-3);
  margin: 0;
}

.stats div {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
}

.stats dt {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.stats dd {
  margin: 2px 0 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.sprints {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.sprints th {
  padding: 8px 10px;
  background: var(--color-surface-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  text-align: left;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary);
}

.sprints td {
  padding: 8px 10px;
  border-top: 1px solid var(--color-border);
}

.sprints .num {
  text-align: right;
}
</style>
