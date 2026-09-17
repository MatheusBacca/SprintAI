<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Ban, Calendar, Check, CircleUser, Clock, Component, Copy, Flag, Layers, Sparkles, SquareKanban, Tag, UserPen } from 'lucide-vue-next'
import AdfRenderer from './AdfRenderer.js'
import IssueRef from './IssueRef.vue'
import { copyRichText } from '@/utils/clipboard'

const props = defineProps({
  issue: { type: Object, required: true },
})
const emit = defineEmits(['open'])

const dateTime = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
const fmt = (value) => (value ? dateTime.format(new Date(value)) : '—')
const dueFmt = (value) => (value ? dateTime.format(new Date(`${value}T12:00:00`)) : '—')

/**
 * "É bloqueada por" segue a regra do card: só lista quem ainda não abriu PR (nem
 * concluiu). A aba Dependências continua com todos os vínculos.
 */
const pendingBlockers = computed(() => {
  const pending = new Set(props.issue.blockers_without_pr ?? [])
  return props.issue.blocked_by.filter((b) => pending.has(b.key))
})

// --- Copiar a descrição --------------------------------------------------------

const COPY_FEEDBACK_MS = 2000
const description = ref(null)
// null | 'ok' | 'erro'
const copyState = ref(null)
let copyTimer = null

const hasDescription = computed(() => Boolean(props.issue.description_adf || props.issue.description_text?.trim()))
const copyLabel = computed(() => ({ ok: 'Descrição copiada', erro: 'Não deu para copiar' })[copyState.value] ?? 'Copiar a descrição')

/**
 * Formatada (colar no Slack ou no Jira mantém listas e negrito) e em texto puro. O HTML
 * sai do que o AdfRenderer já desenhou na tela; o texto, do `description_text` do espelho,
 * com o texto visível como plano B.
 */
async function copyDescription() {
  const el = description.value?.$el ?? description.value
  const text = props.issue.description_text?.trim() || el?.innerText || ''
  const ok = await copyRichText({ html: el?.innerHTML ?? null, text })
  copyState.value = ok ? 'ok' : 'erro'
  clearTimeout(copyTimer)
  copyTimer = setTimeout(() => (copyState.value = null), COPY_FEEDBACK_MS)
}

onBeforeUnmount(() => clearTimeout(copyTimer))

const fields = computed(() => {
  const i = props.issue
  return [
    { icon: Sparkles, label: 'Story Points', value: i.story_points ?? '—' },
    { icon: SquareKanban, label: 'Sprint', value: i.sprints.map((s) => s.name).join(', ') || '—' },
    { icon: Flag, label: 'Prioridade', value: i.priority ?? '—' },
    { icon: Component, label: 'Componente', value: i.components.join(', ') || '—' },
    { icon: Tag, label: 'Labels', value: i.labels.join(', ') || '—' },
    { icon: CircleUser, label: 'Responsável', value: i.assignee_name ?? 'Sem responsável' },
    { icon: UserPen, label: 'Relator', value: i.reporter_name ?? '—' },
    { icon: Calendar, label: 'Entrega', value: dueFmt(i.due_date) },
    { icon: Clock, label: 'Criado em', value: fmt(i.created_at) },
    { icon: Clock, label: 'Atualizado em', value: fmt(i.updated_at) },
  ]
})
</script>

<template>
  <div class="details">
    <section class="details__section">
      <h2 class="details__heading">
        Descrição (Jira)
        <button
          v-if="hasDescription"
          type="button"
          class="details__copy"
          :class="{ 'details__copy--ok': copyState === 'ok', 'details__copy--error': copyState === 'erro' }"
          :title="copyLabel"
          :aria-label="copyLabel"
          @click="copyDescription"
        >
          <Check v-if="copyState === 'ok'" :size="13" />
          <Copy v-else :size="13" />
          <span v-if="copyState" class="details__copy-text">{{ copyState === 'ok' ? 'Copiada' : 'Falhou' }}</span>
        </button>
      </h2>
      <AdfRenderer ref="description" :doc="issue.description_adf" :fallback="issue.description_text" class="details__description" />
    </section>

    <dl class="details__fields">
      <div v-for="f in fields" :key="f.label" class="details__field">
        <dt><component :is="f.icon" :size="15" /> {{ f.label }}</dt>
        <dd>{{ f.value }}</dd>
      </div>
    </dl>

    <section v-if="issue.parent || issue.children.length" class="details__section">
      <h2 class="details__heading"><Layers :size="15" /> Hierarquia</h2>
      <ul class="details__list">
        <IssueRef v-if="issue.parent" :item="issue.parent" @open="emit('open', $event)" />
      </ul>
      <p v-if="issue.children.length" class="details__sub">Filhas ({{ issue.children.length }})</p>
      <ul v-if="issue.children.length" class="details__list">
        <IssueRef v-for="c in issue.children" :key="c.key" :item="c" @open="emit('open', $event)" />
      </ul>
    </section>

    <section v-if="issue.blocks.length" class="details__section">
      <h2 class="details__heading"><Ban :size="15" /> Bloqueia ({{ issue.blocks.length }})</h2>
      <ul class="details__list">
        <IssueRef v-for="b in issue.blocks" :key="b.key" :item="b" @open="emit('open', $event)" />
      </ul>
      <p class="details__hint">
        Esta tarefa bloqueia {{ issue.blocks.length }} {{ issue.blocks.length === 1 ? 'outra tarefa' : 'outras tarefas' }}.
        Finalize ou avance para liberar o fluxo da sprint.
      </p>
    </section>

    <section v-if="pendingBlockers.length" class="details__section">
      <h2 class="details__heading details__heading--alert"><Ban :size="15" /> É bloqueada por ({{ pendingBlockers.length }})</h2>
      <ul class="details__list">
        <IssueRef v-for="b in pendingBlockers" :key="b.key" :item="b" @open="emit('open', $event)" />
      </ul>
    </section>
  </div>
</template>

<style scoped>
.details {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.details__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.details__heading {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
}

.details__copy {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font: inherit;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
}

.details__copy:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.details__copy--ok {
  color: var(--color-success);
}

.details__copy--error {
  color: var(--color-error);
}

.details__heading--alert {
  color: var(--color-error);
}

.details__sub {
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.details__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.details__hint {
  display: flex;
  gap: var(--space-2);
  margin: var(--space-2) 0 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.details__fields {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.details__field {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: var(--space-3);
  padding: 6px 0;
  font-size: var(--text-sm);
}

.details__field dt {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary);
}

.details__field dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 500;
}

/* Conteúdo ADF (renderizado por função, não por HTML cru) */
.details__description {
  font-size: var(--text-sm);
  line-height: 21px;
  color: var(--color-text);
}

.details__description :deep(p) {
  margin: 0 0 var(--space-2);
}

.details__description :deep(ul),
.details__description :deep(ol) {
  margin: 0 0 var(--space-2);
  padding-left: var(--space-5);
}

.details__description :deep(.adf-heading) {
  margin: var(--space-3) 0 var(--space-1);
  font-size: var(--text-sm);
  font-weight: 700;
}

.details__description :deep(a) {
  color: var(--color-primary);
  overflow-wrap: anywhere;
}

.details__description :deep(.adf-code) {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--color-surface-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.details__description :deep(.adf-pre) {
  overflow-x: auto;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.details__description :deep(blockquote) {
  margin: 0 0 var(--space-2);
  padding-left: var(--space-3);
  border-left: 3px solid var(--color-border-strong);
  color: var(--color-text-secondary);
}

.details__description :deep(.adf-panel) {
  margin: 0 0 var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-info-surface-soft);
}

.details__description :deep(.adf-panel--warning) {
  background: var(--color-warning-surface-soft);
}

.details__description :deep(.adf-panel--error) {
  background: var(--color-error-surface);
}

.details__description :deep(.adf-panel--success) {
  background: var(--color-success-surface-soft);
}

.details__description :deep(.adf-mention),
.details__description :deep(.adf-status) {
  padding: 0 4px;
  border-radius: 4px;
  background: var(--color-surface-muted);
  font-weight: 500;
}

.details__description :deep(.adf-media) {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.details__description :deep(.adf-table-wrap) {
  overflow-x: auto;
}

.details__description :deep(.adf-table) {
  border-collapse: collapse;
  font-size: var(--text-xs);
}

.details__description :deep(.adf-table td),
.details__description :deep(.adf-table th) {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  vertical-align: top;
}

.details__description :deep(.adf--empty) {
  color: var(--color-text-muted);
}
</style>
