<script setup>
import { computed } from 'vue'
import { CalendarClock, CircleHelp, History } from 'lucide-vue-next'
import StatusChip from '@/components/jira/StatusChip.vue'
import StoryPointsChip from '@/components/jira/StoryPointsChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'

const props = defineProps({
  issue: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  // Mostrar a data de entrega (blocos de prazo) e/ou a sprint de onde a tarefa sobrou.
  showDue: { type: Boolean, default: false },
  today: { type: String, default: null },
})
const emit = defineEmits(['open'])

const dayFormat = new Intl.DateTimeFormat('pt-BR', { weekday: 'short', day: '2-digit', month: 'short' })

const done = computed(() => props.issue.status_category === 'done')
const late = computed(() => !done.value && props.today && props.issue.due_date && props.issue.due_date < props.today)
const dueLabel = computed(() => (props.issue.due_date ? dayFormat.format(new Date(`${props.issue.due_date}T12:00:00`)) : null))
const leftover = computed(() => props.issue.sprint_state === 'closed' && !done.value)
</script>

<template>
  <li
    class="wrow"
    :class="{ 'wrow--done': done, 'wrow--selected': selected }"
    :data-key="issue.key"
  >
    <button type="button" class="wrow__main" :aria-current="selected ? 'true' : undefined" @click="emit('open', issue.key)">
      <span class="wrow__line">
        <strong class="wrow__key">{{ issue.key }}</strong>
        <span class="wrow__summary" :title="issue.summary">{{ issue.summary }}</span>
      </span>
      <span class="wrow__meta">
        <span v-if="showDue && dueLabel" class="wrow__due" :class="{ 'wrow__due--late': late }">
          <CalendarClock :size="12" /> {{ dueLabel }}
        </span>
        <span v-if="leftover" class="wrow__leftover" :title="`Não foi para a sprint seguinte`">
          <History :size="12" /> sobrou da {{ issue.sprint_name }}
        </span>
        <span v-else-if="issue.sprint_name && issue.sprint_state !== 'closed'" class="wrow__sprint">{{ issue.sprint_name }}</span>
        <span v-if="issue.open_points" class="wrow__points" :title="`${issue.open_points} ponto(s) em aberto nos contextos`">
          <CircleHelp :size="12" /> {{ issue.open_points }}
        </span>
        <span v-if="issue.parent_summary" class="wrow__parent" :title="issue.parent_summary">{{ issue.parent_summary }}</span>
      </span>
    </button>
    <!-- Status, SP e PR ficam fora do botão da linha: cada um é um botão (ou link) próprio,
         e botão dentro de botão não existe em HTML. -->
    <span class="wrow__side">
      <StatusChip class="wrow__status" :data-category="issue.status_category" :issue-key="issue.key" :status="issue.status" />
      <StoryPointsChip v-if="issue.story_points != null" class="wrow__sp" :issue-key="issue.key" :points="issue.story_points" />
      <PrStatusBadge
        v-if="issue.pr"
        :status="issue.pr.status"
        :pr-count="issue.pr.pr_count"
        :build-failed="issue.pr.build_failed"
        :links="issue.pr.links ?? []"
        :issue-key="issue.key"
        size="sm"
      />
    </span>
  </li>
</template>

<style scoped>
.wrow {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 2px 0;
}

.wrow + .wrow {
  border-top: 1px solid var(--color-border);
}

.wrow__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 8px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  font: inherit;
  text-align: left;
}

.wrow__main:hover,
.wrow--selected .wrow__main {
  background: var(--color-primary-soft);
}

.wrow__line {
  display: flex;
  gap: var(--space-2);
  min-width: 0;
  font-size: var(--text-sm);
}

.wrow__key {
  flex-shrink: 0;
  color: var(--color-primary);
  white-space: nowrap;
}

.wrow__summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.wrow--done .wrow__summary {
  color: var(--color-text-muted);
  text-decoration: line-through;
}

.wrow__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  min-width: 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.wrow__status {
  max-width: 180px;
  padding: 0 6px;
  border: 0;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  color: var(--color-text-secondary);
}

.wrow__status[data-category='done'] {
  background: var(--color-success-surface);
  color: var(--color-success);
}

.wrow__status[data-category='indeterminate'] {
  background: var(--color-info-surface);
  color: var(--color-info);
}

.wrow__due,
.wrow__leftover,
.wrow__points {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 600;
}

.wrow__due--late {
  color: var(--color-error);
}

.wrow__leftover,
.wrow__points {
  color: var(--color-warning-text);
}

.wrow__parent {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wrow__side {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.wrow__sp {
  padding: 0 4px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
</style>
