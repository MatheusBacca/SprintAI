<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowRight, CalendarClock, Inbox, ListChecks, Scissors } from 'lucide-vue-next'
import WeekIssueRow from '@/components/week/WeekIssueRow.vue'

const props = defineProps({
  pending: { type: Object, default: null },
  today: { type: String, default: null },
  selectedKey: { type: String, default: null },
})
defineEmits(['open'])

/** Mesmos blocos da Semana, só que o topo de cada um. */
const blocks = computed(() => {
  const p = props.pending
  if (!p) return []
  return [
    { id: 'overdue', title: 'Atrasadas', icon: CalendarClock, items: p.overdue, showDue: true, tone: 'late' },
    { id: 'due', title: 'Prazo nesta semana', icon: CalendarClock, items: p.due, showDue: true },
    { id: 'slicing', title: 'Analisar e fatiar', icon: Scissors, items: p.slicing },
    { id: 'without_sprint', title: 'Sem sprint', icon: Inbox, items: p.without_sprint, showDue: true },
  ].filter((block) => block.items.length)
})

const shown = computed(() => blocks.value.reduce((total, b) => total + b.items.length, 0))
const hidden = computed(() => Math.max(0, (props.pending?.total ?? 0) - shown.value))
</script>

<template>
  <article class="card pending" data-block="pending">
    <header class="pending__head">
      <h2 class="pending__title"><ListChecks :size="16" /> Pendências da semana</h2>
      <RouterLink to="/semana" class="pending__link">
        ver Semana <ArrowRight :size="12" />
      </RouterLink>
    </header>

    <template v-for="block in blocks" :key="block.id">
      <h3 class="pending__sub" :data-tone="block.tone">
        <component :is="block.icon" :size="12" /> {{ block.title }} <small>{{ block.items.length }}</small>
      </h3>
      <ul class="pending__list">
        <WeekIssueRow
          v-for="issue in block.items"
          :key="issue.key"
          :issue="issue"
          :today="today"
          :show-due="block.showDue"
          :selected="issue.key === selectedKey"
          @open="(key) => $emit('open', key)"
        />
      </ul>
    </template>

    <p v-if="!blocks.length" class="pending__empty">
      Nada pendente: sem atraso, sem prazo estourando e nada solto fora de sprint.
    </p>
    <p v-else-if="hidden" class="pending__more">
      e mais {{ hidden }} na <RouterLink to="/semana">Semana</RouterLink>.
    </p>
  </article>
</template>

<style scoped>
.pending {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
}

.pending__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.pending__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.pending__title svg {
  color: var(--color-primary);
}

.pending__link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.pending__sub {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: var(--space-3) 0 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.pending__sub[data-tone='late'] {
  color: var(--color-error);
}

.pending__sub small {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  letter-spacing: 0;
  color: var(--color-text-secondary);
}

.pending__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.pending__empty,
.pending__more {
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.pending__more a {
  font-weight: 600;
  color: var(--color-primary);
}
</style>
