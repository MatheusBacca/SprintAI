<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertTriangle, ChevronRight, Target } from 'lucide-vue-next'

import ActivityKindIcon from '@/components/activity/ActivityKindIcon.vue'
import { activityKindMeta, activityTab } from '@/constants/activityKinds'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  sprints: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selectedKey: { type: String, default: null },
})
const emit = defineEmits(['open'])

const dayFormat = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short' })
const asDate = (d) => new Date(`${d}T12:00:00`)
const percent = (value) => `${Math.round((value ?? 0) * 100)}%`

const bars = computed(() =>
  props.sprints.map((sprint) => ({
    ...sprint,
    range:
      sprint.start && sprint.end
        ? `${dayFormat.format(asDate(sprint.start))} – ${dayFormat.format(asDate(sprint.end))}`
        : null,
    // Atrás do esperado por mais de 10 pontos: a barra avisa em vez de só informar.
    behind: sprint.expected != null && sprint.real < sprint.expected - 0.1,
    updates: (sprint.updates ?? []).map((update) => ({
      ...update,
      meta: activityKindMeta(update.kind),
      ago: formatRelative(update.occurred_at),
    })),
  })),
)
</script>

<template>
  <article class="card sprints">
    <h2 class="sprints__title"><Target :size="16" /> Progresso da sprint</h2>

    <p v-if="loading && !sprints.length" class="sprints__empty">Carregando…</p>
    <p v-else-if="!sprints.length" class="sprints__empty">
      Nenhuma sprint ativa com tarefa sua em aberto. Uma sprint aparece aqui enquanto tiver
      trabalho seu por fazer — mesmo depois de passar da data de fim.
    </p>

    <ul v-else class="sprints__list">
      <li v-for="sprint in bars" :key="sprint.sprint_id" class="sprint" :data-sprint="sprint.sprint_id">
        <header class="sprint__head">
          <RouterLink
            :to="{ name: 'sprints', query: { sprint: sprint.sprint_id } }"
            class="sprint__name"
            :title="`Abrir a árvore de ${sprint.name}`"
          >
            {{ sprint.name }} <ChevronRight :size="13" />
          </RouterLink>
          <span v-if="sprint.range" class="sprint__range">{{ sprint.range }}</span>
          <span
            v-if="sprint.overdue_active"
            class="sprint__flag"
            title="A sprint passou da data de fim e continua ativa no Jira"
          >
            <AlertTriangle :size="12" /> vencida
          </span>
          <span class="sprint__value" :data-behind="sprint.behind || null">{{ percent(sprint.real) }}</span>
        </header>

        <div
          class="sprint__track"
          role="progressbar"
          :aria-valuenow="Math.round(sprint.real * 100)"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="`Progresso de ${sprint.name}`"
        >
          <div class="sprint__fill" :data-behind="sprint.behind || null" :style="{ width: percent(sprint.real) }" />
          <div
            v-if="sprint.expected != null"
            class="sprint__expected"
            :style="{ left: percent(sprint.expected) }"
            :title="`Esperado para hoje: ${percent(sprint.expected)} do tempo útil da sprint`"
          />
        </div>

        <p class="sprint__meta">
          {{ sprint.done_count }}/{{ sprint.issue_count }} tarefas · {{ sprint.story_points }} SP
          <template v-if="sprint.expected != null"> · esperado {{ percent(sprint.expected) }}</template>
        </p>

        <!-- O que mexeram nas minhas tarefas desta sprint nas últimas 48h -->
        <template v-if="sprint.updates.length">
          <h3 class="sprint__updates-title">
            Mexeram nestas <small>{{ sprint.updates.length }}</small>
          </h3>
          <ul class="updates">
            <li
              v-for="update in sprint.updates"
              :key="update.key"
              class="update"
              :data-key="update.key"
              :class="{ 'update--selected': update.key === selectedKey }"
            >
              <button type="button" class="update__btn" @click="emit('open', update.key, activityTab(update.kind))">
                <span class="update__line">
                  <strong class="update__key">{{ update.key }}</strong>
                  <span v-if="update.event_count > 1" class="update__count">{{ update.event_count }}</span>
                  <span class="update__ago">{{ update.ago }}</span>
                </span>
                <span class="update__summary" :title="update.summary">{{ update.summary }}</span>
                <span class="update__what">
                  <ActivityKindIcon :kind="update.kind" :size="12" />
                  <span class="update__text">
                    {{ update.actor_name ?? 'Alguém' }} {{ update.meta.text }}
                    <strong v-if="update.title">{{ update.title }}</strong>
                  </span>
                </span>
              </button>
            </li>
          </ul>
        </template>
      </li>
    </ul>
  </article>
</template>

<style scoped>
.sprints {
  padding: var(--space-4);
}

.sprints__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
  font-size: var(--text-md);
  font-weight: 600;
}

.sprints__title svg {
  color: var(--color-primary);
}

.sprints__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.sprints__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  margin: 0;
  padding: 0;
  list-style: none;
}

.sprint__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin-bottom: 6px;
}

.sprint__name {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: var(--text-sm);
  font-weight: 600;
}

.sprint__name:hover {
  color: var(--color-primary);
  text-decoration: underline;
}

.sprint__name svg {
  color: var(--color-text-muted);
}

.sprint__range {
  font-size: 11px;
  color: var(--color-text-muted);
}

.sprint__flag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-warning-surface);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-warning-text);
}

.sprint__value {
  margin-left: auto;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-primary);
}

.sprint__value[data-behind] {
  color: var(--color-warning);
}

.sprint__track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  overflow: hidden;
}

.sprint__fill {
  height: 100%;
  border-radius: 999px;
  background: var(--color-primary);
  transition: width var(--duration-normal, 0.2s) ease;
}

.sprint__fill[data-behind] {
  background: var(--color-warning);
}

/* Marcador do "esperado": a linha que a barra real persegue. */
.sprint__expected {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  background: var(--color-text-secondary);
  transform: translateX(-1px);
}

.sprint__meta {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.sprint__updates-title {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: var(--space-3) 0 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.sprint__updates-title small {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  letter-spacing: 0;
  color: var(--color-text-secondary);
}

/* Rolagem horizontal própria: a linha nunca empurra a largura da página. */
.updates {
  display: flex;
  gap: var(--space-2);
  margin: 0;
  padding: 0 0 var(--space-2);
  list-style: none;
  overflow-x: auto;
  scroll-snap-type: x proximity;
}

.update {
  flex: 0 0 auto;
  width: 230px;
  scroll-snap-align: start;
}

.update__btn {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font: inherit;
  text-align: left;
}

.update__btn:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.update--selected .update__btn {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.update__line {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--text-xs);
}

.update__key {
  color: var(--color-primary);
}

.update__count {
  padding: 0 5px;
  border-radius: 999px;
  background: var(--color-primary);
  font-size: 10px;
  font-weight: 600;
  color: var(--color-on-primary);
}

.update__ago {
  margin-left: auto;
  font-size: 10px;
  font-style: italic;
  color: var(--color-text-muted);
}

.update__summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-xs);
  color: var(--color-text);
}

.update__what {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.update__text {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.update__text strong {
  color: var(--color-text-secondary);
}
</style>
