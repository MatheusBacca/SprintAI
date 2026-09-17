<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Ban, Layers, SquareCheck, StickyNote, X } from 'lucide-vue-next'
import IssueContextsTab from './IssueContextsTab.vue'
import IssueDependenciesTab from './IssueDependenciesTab.vue'
import IssueDetailsTab from './IssueDetailsTab.vue'
import IssueHistoryTab from './IssueHistoryTab.vue'
import IssueNotesTab from './IssueNotesTab.vue'
import IssuePullRequestsTab from './IssuePullRequestsTab.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { useContextsStore } from '@/stores/contexts'
import { useIssueDetailStore } from '@/stores/issueDetail'
import { useNotesStore } from '@/stores/notes'
import { useRefreshStore } from '@/stores/refresh'
import { useUiStore } from '@/stores/ui'
import { safeUrl } from '@/utils/safeUrl'

const props = defineProps({
  issueKey: { type: String, required: true },
})
const emit = defineEmits(['close', 'open', 'ready'])

const store = useIssueDetailStore()
const notes = useNotesStore()
const contexts = useContextsStore()
const refresh = useRefreshStore()
const ui = useUiStore()
const tab = ref('detalhes')
// Contagem vem da própria aba (e de uma consulta leve ao abrir o painel).
const notesCount = ref(null)
const contextsCount = ref(null)
// As duas contagens voltaram (com sucesso ou não) para a tarefa da vez.
const countsSettled = ref(false)

const entry = computed(() => store.issues[props.issueKey] ?? { data: null, loading: true, error: null })
const issue = computed(() => entry.value.data)
// Mesma regra do card do canvas: ícone de bloqueio só enquanto algum bloqueador não abriu PR.
const waitingBlocker = computed(() => (issue.value?.blockers_without_pr ?? []).length > 0)
// Contorno na cor da etapa do status, a mesma do card. Sem etapa, fica a borda padrão.
const toneStyle = computed(() => (issue.value?.stage ? { '--tone': issue.value.stage.color } : null))

/**
 * Lembretes saíram da fileira de abas para o ícone do cabeçalho — o mesmo do rodapé do
 * card no canvas. Clicar de novo volta para os detalhes: sem aba marcada, o ícone é o
 * único jeito de saber (e de sair de) onde se está.
 */
const notesOpen = computed(() => tab.value === 'lembretes')
function toggleNotes() {
  tab.value = notesOpen.value ? 'detalhes' : 'lembretes'
}

function loadCounts(key, { reset = true } = {}) {
  if (reset) {
    notesCount.value = null
    contextsCount.value = null
    countsSettled.value = false
  }
  Promise.allSettled([
    contexts.forIssue(key).then((r) => { if (props.issueKey === key) contextsCount.value = r.own.length + r.linked.length }),
    notes.fetch({ issue_key: key, limit: 1 }).then((r) => { if (props.issueKey === key) notesCount.value = r.total }),
  ]).then(() => { if (props.issueKey === key) countsSettled.value = true })
}

/**
 * Tarefa, contagens das abas e do ícone de lembretes já chegaram (ou falharam). Quem
 * anima a entrada do painel espera por isto para mostrar tudo de uma vez, sem o título
 * chegar antes do selo de status e as contagens pipocarem depois.
 */
const ready = computed(() => countsSettled.value && !entry.value.loading && Boolean(issue.value || entry.value.error))
watch(ready, (value) => { if (value) emit('ready') }, { immediate: true })

watch(
  () => props.issueKey,
  (key) => {
    store.load(key)
    tab.value = ui.consumeIssueTab(key) ?? 'detalhes'
    loadCounts(key)
  },
  { immediate: true },
)

// Sync ou "Recarregar": o painel aberto se refaz sozinho, sem trocar a aba nem
// piscar (o store segura o que está na tela enquanto busca).
watch(() => refresh.revision, () => {
  store.load(props.issueKey)
  loadCounts(props.issueKey, { reset: false })
})

// Painel já aberto na mesma tarefa e a busca pede outra aba.
watch(
  () => ui.issueTabRequest,
  () => {
    const requested = ui.consumeIssueTab(props.issueKey)
    if (requested) tab.value = requested
  },
)

const tabs = computed(() => {
  const i = issue.value
  const depCount = i ? i.dependencies.reduce((n, g) => n + g.items.length, 0) + i.children.length + (i.parent ? 1 : 0) : 0
  return [
    { id: 'detalhes', label: 'Detalhes' },
    { id: 'dependencias', label: 'Dependências', count: depCount },
    { id: 'prs', label: 'PRs', count: i?.pull_requests.pr_count ?? 0 },
    { id: 'historico', label: 'Histórico', count: i?.comments.length || null },
    { id: 'contextos', label: 'Contextos', count: contextsCount.value || null },
  ]
})

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <aside class="drawer card" :class="{ 'drawer--toned': toneStyle }" :style="toneStyle" role="complementary" :aria-label="`Tarefa ${issueKey}`">
    <span v-if="issue" class="drawer__status" :title="`Status no Jira: ${issue.status}`">{{ issue.status }}</span>

    <header class="drawer__header">
      <div class="drawer__bar">
        <span v-if="issue" class="drawer__icon" :data-blocked="waitingBlocker || null">
          <Ban v-if="waitingBlocker" :size="15" />
          <Layers v-else-if="issue.children.length" :size="15" />
          <SquareCheck v-else :size="15" />
        </span>
        <span class="drawer__type">{{ issue?.issue_type?.toUpperCase() ?? '…' }}</span>
        <a v-if="safeUrl(issue?.url)" :href="safeUrl(issue.url)" target="_blank" rel="noopener noreferrer" class="drawer__key drawer__key--link" title="Abrir no Jira">
          {{ issueKey }}
        </a>
        <span v-else class="drawer__key">{{ issueKey }}</span>
        <!-- SP e PR na linha da chave, como no card do canvas: o título e as abas sobem. -->
        <template v-if="issue">
          <span v-if="issue.story_points != null" class="drawer__chip">{{ issue.story_points }} SP</span>
          <PrStatusBadge :status="issue.pull_requests.status" :pr-count="issue.pull_requests.pr_count" :build-failed="issue.pull_requests.build_failed" size="sm" />
        </template>
        <button
          type="button"
          class="drawer__action drawer__action--first drawer__notes"
          :class="{ 'drawer__action--active': notesOpen }"
          :title="notesOpen ? 'Voltar aos detalhes' : 'Lembretes desta tarefa'"
          aria-label="Lembretes"
          :aria-pressed="notesOpen"
          @click="toggleNotes"
        >
          <StickyNote :size="15" />
          <span v-if="notesCount" class="drawer__notes-count">{{ notesCount }}</span>
        </button>
        <button type="button" class="drawer__action" title="Fechar (Esc)" aria-label="Fechar painel" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>

      <h2 class="drawer__title">{{ issue?.summary ?? (entry.loading ? 'Carregando…' : issueKey) }}</h2>

      <nav v-if="issue" class="drawer__tabs" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          role="tab"
          class="drawer__tab"
          :class="{ 'drawer__tab--active': tab === t.id }"
          :aria-selected="tab === t.id"
          @click="tab = t.id"
        >
          {{ t.label }}<span v-if="t.count" class="drawer__count">{{ t.count }}</span>
        </button>
      </nav>
    </header>

    <div class="drawer__body">
      <p v-if="entry.error && !issue" class="drawer__error" role="alert">{{ entry.error }}</p>
      <template v-else-if="issue">
        <IssueDetailsTab v-if="tab === 'detalhes'" :issue="issue" @open="emit('open', $event)" />
        <IssueDependenciesTab v-else-if="tab === 'dependencias'" :issue="issue" @open="emit('open', $event)" />
        <IssuePullRequestsTab v-else-if="tab === 'prs'" :summary="issue.pull_requests" />
        <IssueHistoryTab v-else-if="tab === 'historico'" :key="issue.key" :issue="issue" />
        <IssueContextsTab v-else-if="tab === 'contextos'" :issue-key="issue.key" @open="emit('open', $event)" @count="contextsCount = $event" />
        <IssueNotesTab v-else :issue-key="issue.key" @open="emit('open', $event)" @count="notesCount = $event" />
      </template>
    </div>
  </aside>
</template>

<style scoped>
/* Sem overflow: hidden — o status senta em cima do contorno, metade para fora. Quem
   rola é só o corpo. */
.drawer {
  position: relative;
  width: min(480px, 42vw);
  min-width: 360px;
  display: flex;
  flex-direction: column;
}

/* Mesma espessura e mistura do contorno do card no canvas. */
.drawer--toned {
  border: 1.5px solid color-mix(in srgb, var(--tone) 70%, transparent);
}

.drawer__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5) 0;
  border-bottom: 1px solid var(--color-border);
}

.drawer__bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.drawer__icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.drawer__icon[data-blocked] {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.drawer__type {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary);
}

.drawer__key {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.drawer__key--link {
  color: var(--color-primary);
  text-decoration: none;
}

.drawer__key--link:hover {
  text-decoration: underline;
}

.drawer__action--first {
  margin-left: auto;
}

.drawer__action {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.drawer__action--active {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.drawer__notes {
  position: relative;
}

.drawer__notes-count {
  position: absolute;
  top: -3px;
  right: -4px;
  box-sizing: border-box;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--color-primary);
  font-size: 10px;
  font-weight: 700;
  line-height: 15px;
  color: var(--color-on-primary);
}

.drawer__action:hover:not(:disabled) {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.drawer__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  line-height: 24px;
  letter-spacing: -0.01em;
}

.drawer__chip {
  flex-shrink: 0;
  white-space: nowrap;
  padding: 1px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

/* Mesmo selo do card do canvas: status do Jira sentado no contorno, com fundo opaco
   para a borda não atravessar o texto. */
.drawer__status {
  position: absolute;
  top: -9px;
  left: var(--space-5);
  z-index: 1;
  box-sizing: border-box;
  max-width: calc(100% - 2 * var(--space-5));
  height: 18px;
  padding: 0 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1.5px solid var(--tone, var(--color-border-strong));
  border-radius: 999px;
  background: color-mix(in srgb, var(--tone, var(--color-border-strong)) 16%, var(--color-surface));
  font-size: 10px;
  font-weight: 600;
  line-height: 15px;
  letter-spacing: 0.2px;
  color: var(--color-text);
}

.drawer__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--space-4);
  margin-top: var(--space-2);
}

.drawer__tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: var(--space-2) 0 10px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.drawer__tab--active {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}

.drawer__count {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
}

.drawer__body {
  flex: 1;
  min-height: 0;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  overflow-y: auto;
  padding: var(--space-4) var(--space-5) var(--space-6);
}

.drawer__error {
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}
</style>
