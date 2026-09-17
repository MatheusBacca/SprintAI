<script setup>
import { computed, onMounted, watch } from 'vue'
import { History, MessageSquare, RefreshCw } from 'lucide-vue-next'
import AdfRenderer from './AdfRenderer.js'
import { useIssueDetailStore } from '@/stores/issueDetail'
import { useRefreshStore } from '@/stores/refresh'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  issue: { type: Object, required: true },
})

const store = useIssueDetailStore()
const refresh = useRefreshStore()
const changelog = computed(() => store.changelogs[props.issue.key] ?? { data: null, loading: false, error: null })

onMounted(() => store.loadChangelog(props.issue.key))
// O changelog vem ao vivo do Jira: depois de um sync ou de um "Recarregar", vale
// buscar de novo — é onde a mudança que disparou o sync costuma aparecer.
watch(() => refresh.revision, () => store.loadChangelog(props.issue.key))

const FIELD_LABELS = {
  status: 'Status',
  assignee: 'Responsável',
  summary: 'Título',
  description: 'Descrição',
  priority: 'Prioridade',
  Sprint: 'Sprint',
  'Story Points': 'Story Points',
  labels: 'Labels',
  Component: 'Componente',
  duedate: 'Entrega',
  resolution: 'Resolução',
  Link: 'Link',
  'Epic Link': 'Épico',
  IssueParentAssociation: 'Pai',
  Attachment: 'Anexo',
}

// Comentários (espelho) + mudanças (Jira ao vivo) numa só linha do tempo, mais recente primeiro.
const timeline = computed(() => {
  const comments = props.issue.comments.map((c) => ({ kind: 'comment', id: `c${c.id}`, at: c.created_at, author: c.author_name, comment: c }))
  const changes = (changelog.value.data?.entries ?? []).map((e) => ({ kind: 'change', id: `h${e.id}`, at: e.created_at, author: e.author_name, items: e.items }))
  return [...comments, ...changes].sort((a, b) => new Date(b.at) - new Date(a.at))
})

const dateTime = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
</script>

<template>
  <div class="history">
    <p v-if="changelog.loading" class="history__note">
      <RefreshCw :size="13" class="spin" /> Buscando histórico de mudanças no Jira…
    </p>
    <p v-else-if="changelog.error" class="history__note history__note--error" role="alert">
      Histórico de mudanças indisponível: {{ changelog.error }}
      <button type="button" class="btn btn--secondary" @click="store.loadChangelog(issue.key, { force: true })">Tentar de novo</button>
    </p>
    <p v-else-if="changelog.data?.truncated" class="history__note">Mostrando as 200 mudanças mais recentes.</p>

    <ol v-if="timeline.length" class="history__list">
      <li v-for="event in timeline" :key="event.id" class="event" :data-kind="event.kind">
        <span class="event__icon">
          <MessageSquare v-if="event.kind === 'comment'" :size="13" />
          <History v-else :size="13" />
        </span>
        <div class="event__body">
          <p class="event__head">
            <strong>{{ event.author ?? 'Alguém' }}</strong>
            {{ event.kind === 'comment' ? 'comentou' : 'alterou' }}
            <time :datetime="event.at" :title="dateTime.format(new Date(event.at))">{{ formatRelative(event.at) }}</time>
          </p>
          <AdfRenderer v-if="event.kind === 'comment'" :doc="event.comment.body_adf" :fallback="event.comment.body_text" class="event__comment" />
          <ul v-else class="event__changes">
            <li v-for="(item, i) in event.items" :key="i">
              <span class="event__field">{{ FIELD_LABELS[item.field] ?? item.field }}</span>
              <template v-if="item.from_value"><s>{{ item.from_value }}</s> → </template>
              <span>{{ item.to_value ?? '(vazio)' }}</span>
            </li>
          </ul>
        </div>
      </li>
    </ol>
    <p v-else-if="!changelog.loading" class="history__note">Sem comentários ou mudanças registradas.</p>
  </div>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.history__note {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.history__note--error {
  color: var(--color-error);
}

.history__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.event {
  position: relative;
  display: flex;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
}

.event:not(:last-child)::before {
  content: '';
  position: absolute;
  top: 26px;
  bottom: 0;
  left: 12px;
  border-left: 1px solid var(--color-border);
}

.event__icon {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 25px;
  height: 25px;
  border-radius: 50%;
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
}

.event[data-kind='comment'] .event__icon {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.event__body {
  flex: 1;
  min-width: 0;
}

.event__head {
  margin: 3px 0 4px;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.event__head time {
  margin-left: 4px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.event__comment {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  overflow-wrap: anywhere;
}

.event__comment :deep(p) {
  margin: 0 0 4px;
}

.event__changes {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  overflow-wrap: anywhere;
}

.event__field {
  margin-right: 4px;
  font-weight: 600;
  color: var(--color-text);
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
