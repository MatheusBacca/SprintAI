<script setup>
import { computed } from 'vue'
import { Activity, ExternalLink } from 'lucide-vue-next'

import ActivityKindIcon from '@/components/activity/ActivityKindIcon.vue'
import { activityKindMeta, activityTab } from '@/constants/activityKinds'
import { useActivityStore } from '@/stores/activity'
import { formatRelative } from '@/utils/time'
import { safeUrl } from '@/utils/safeUrl'

const props = defineProps({
  today: { type: String, default: null },
  selectedKey: { type: String, default: null },
})
const emit = defineEmits(['open'])

const activity = useActivityStore()

const SOURCES = [
  { id: null, label: 'Tudo' },
  { id: 'jira', label: 'Jira' },
  { id: 'bitbucket', label: 'Bitbucket' },
]

const dayFormat = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: '2-digit', month: 'short' })
const timeFormat = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' })
const isoDay = (date) => date.toISOString().slice(0, 10)

function dayLabel(iso) {
  const date = new Date(iso)
  const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  if (props.today && day === props.today) return 'Hoje'
  const yesterday = new Date(`${props.today ?? isoDay(new Date())}T12:00:00`)
  yesterday.setDate(yesterday.getDate() - 1)
  if (day === isoDay(yesterday)) return 'Ontem'
  return dayFormat.format(date)
}

const days = computed(() =>
  activity.days.map((group) => ({
    ...group,
    label: dayLabel(group.at),
    events: group.events.map((event) => ({
      ...event,
      meta: activityKindMeta(event.kind),
      time: timeFormat.format(new Date(event.occurred_at)),
      ago: formatRelative(event.occurred_at),
      prUrl: safeUrl(event.pr_url),
    })),
  })),
)

function open(event) {
  if (event.issue_key) return emit('open', event.issue_key, activityTab(event.kind))
  // PR sem tarefa no espelho: só resta o Bitbucket.
  if (event.prUrl) window.open(event.prUrl, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <article class="card feed" data-block="activity">
    <header class="feed__head">
      <h2 class="feed__title"><Activity :size="16" /> Atividade</h2>
      <div class="feed__filters">
        <button
          v-for="source in SOURCES"
          :key="source.label"
          type="button"
          class="feed__chip"
          :class="{ 'feed__chip--on': activity.source === source.id }"
          :aria-pressed="activity.source === source.id"
          @click="activity.setFilters({ source: source.id })"
        >
          {{ source.label }}
        </button>
        <button
          type="button"
          class="feed__chip"
          :class="{ 'feed__chip--on': activity.onlyOthers }"
          :aria-pressed="activity.onlyOthers"
          title="Esconde o que fui eu que fiz"
          @click="activity.setFilters({ onlyOthers: !activity.onlyOthers })"
        >
          só de outros
        </button>
      </div>
    </header>

    <p v-if="activity.error" class="feed__error" role="alert">{{ activity.error }}</p>
    <p v-else-if="activity.loading && !days.length" class="feed__empty">Carregando…</p>
    <p v-else-if="!days.length" class="feed__empty">
      Nada por aqui ainda. O feed é preenchido durante a sincronização — as mudanças das suas
      tarefas e dos seus PRs aparecem a partir da próxima.
    </p>

    <template v-for="group in days" :key="group.day">
      <h3 class="feed__day">{{ group.label }}</h3>
      <ul class="feed__list">
        <li
          v-for="event in group.events"
          :key="event.id"
          class="event"
          :data-kind="event.kind"
          :class="{ 'event--selected': event.issue_key && event.issue_key === selectedKey }"
        >
          <button type="button" class="event__main" @click="open(event)">
            <ActivityKindIcon :kind="event.kind" class="event__icon" />
            <span class="event__body">
              <span class="event__line">
                <strong v-if="event.issue_key" class="event__key">{{ event.issue_key }}</strong>
                <span class="event__what">
                  <span class="event__actor">{{ event.actor_is_me ? 'Você' : (event.actor_name ?? 'Alguém') }}</span>
                  {{ event.meta.text }}
                  <strong v-if="event.title" class="event__value">{{ event.title }}</strong>
                </span>
              </span>
              <span class="event__meta">
                <span>{{ event.time }}</span>
                <span class="event__ago">{{ event.ago }}</span>
                <span v-if="event.repo_slug" class="event__repo">{{ event.repo_slug }}#{{ event.pr_id }}</span>
                <span v-if="event.issue_summary" class="event__summary">{{ event.issue_summary }}</span>
              </span>
            </span>
          </button>
          <a
            v-if="event.prUrl"
            :href="event.prUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="event__link"
            title="Abrir o PR no Bitbucket"
          >
            <ExternalLink :size="13" />
          </a>
        </li>
      </ul>
    </template>

    <button
      v-if="activity.hasMore"
      type="button"
      class="btn btn--secondary feed__more"
      :disabled="activity.loadingMore"
      @click="activity.loadMore()"
    >
      {{ activity.loadingMore ? 'Carregando…' : 'Carregar mais' }}
    </button>
  </article>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-4);
}

.feed__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
  margin-bottom: var(--space-2);
}

.feed__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.feed__title svg {
  color: var(--color-primary);
}

.feed__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: auto;
}

.feed__chip {
  padding: 3px 9px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.feed__chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.feed__chip--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.feed__error {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-error);
}

.feed__empty {
  margin: var(--space-2) 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.feed__day {
  margin: var(--space-3) 0 2px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.feed__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.event {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.event + .event {
  border-top: 1px solid var(--color-border);
}

.event__main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: 7px 8px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  font: inherit;
  text-align: left;
}

.event__main:hover,
.event--selected .event__main {
  background: var(--color-primary-soft);
}

.event__icon {
  display: flex;
  flex-shrink: 0;
  padding-top: 2px;
}

.event__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.event__line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  font-size: var(--text-sm);
}

.event__key {
  flex-shrink: 0;
  color: var(--color-primary);
}

.event__what {
  min-width: 0;
  /* Um valor longo (trecho de comentário, título de PR) quebra em vez de empurrar a
     linha, e para em duas linhas para o feed continuar escaneável. */
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  color: var(--color-text-secondary);
}

.event__actor {
  font-weight: 600;
  color: var(--color-text);
}

.event__value {
  font-weight: 600;
  color: var(--color-text);
}

.event__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  min-width: 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.event__ago {
  font-style: italic;
}

.event__repo {
  font-family: var(--font-mono);
}

.event__summary {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event__link {
  flex-shrink: 0;
  padding: 6px;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
}

.event__link:hover {
  background: var(--color-surface-muted);
  color: var(--color-primary);
}

.feed__more {
  align-self: center;
  margin-top: var(--space-3);
}
</style>
