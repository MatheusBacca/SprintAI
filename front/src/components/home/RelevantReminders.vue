<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowRight, BellRing, Pin, Plus } from 'lucide-vue-next'
import { NOTE_COLORS } from '@/constants/noteColors'
import { useNotesStore } from '@/stores/notes'

const props = defineProps({
  reminders: { type: Array, default: () => [] },
})

const notes = useNotesStore()
const timeFormat = new Intl.DateTimeFormat('pt-BR', {
  weekday: 'short',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

const items = computed(() =>
  props.reminders.map((note) => ({
    ...note,
    when: note.remind_at ? timeFormat.format(new Date(note.remind_at)) : null,
    state: note.reminder_due ? 'due' : note.reminded_at ? 'done' : 'upcoming',
    border: (NOTE_COLORS[note.color] ?? NOTE_COLORS.yellow).border,
  })),
)
</script>

<template>
  <article class="card reminders" data-block="reminders">
    <header class="reminders__head">
      <h2 class="reminders__title"><BellRing :size="16" /> Lembretes relevantes</h2>
      <button type="button" class="reminders__new" @click="notes.openEditor(null)">
        <Plus :size="12" /> Novo
      </button>
      <RouterLink to="/lembretes" class="reminders__link">ver todos <ArrowRight :size="12" /></RouterLink>
    </header>
    <p class="reminders__hint">Vencidos, das próximas 48h, fixados e ligados à sprint ativa.</p>

    <ul v-if="items.length" class="reminders__list">
      <li
        v-for="note in items"
        :key="note.id"
        class="reminder"
        :data-id="note.id"
        :data-state="note.state"
        :style="{ '--note-border': note.border }"
      >
        <button type="button" class="reminder__main" @click="notes.openEditor(note)">
          <span class="reminder__line">
            <Pin v-if="note.pinned" :size="11" class="reminder__pin" />
            <span class="reminder__text">{{ note.title || note.body.slice(0, 80) }}</span>
          </span>
          <span class="reminder__meta">
            <span v-if="note.when" class="reminder__when">{{ note.when }}</span>
            <span v-for="issue in note.issues" :key="issue.key" class="reminder__issue">{{ issue.key }}</span>
          </span>
        </button>
        <button
          v-if="note.reminder_due"
          type="button"
          class="reminder__ack"
          title="Marcar como visto"
          @click="notes.acknowledge(note.id)"
        >
          Concluir
        </button>
      </li>
    </ul>
    <p v-else class="reminders__empty">Nenhum lembrete pedindo atenção agora.</p>
  </article>
</template>

<style scoped>
.reminders {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-4);
}

.reminders__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.reminders__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.reminders__title svg {
  color: var(--color-primary);
}

.reminders__new {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  padding: 3px 8px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.reminders__new:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.reminders__link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.reminders__hint,
.reminders__empty {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.reminders__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.reminder {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 2px 0;
}

.reminder + .reminder {
  border-top: 1px solid var(--color-border);
}

.reminder__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 8px;
  border: 0;
  border-left: 3px solid var(--note-border);
  border-radius: var(--radius-sm);
  background: none;
  font: inherit;
  text-align: left;
}

.reminder__main:hover {
  background: var(--color-surface-muted);
}

.reminder__line {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: var(--text-sm);
}

.reminder__pin {
  flex-shrink: 0;
  color: var(--color-primary);
}

.reminder__text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reminder[data-state='done'] .reminder__text {
  color: var(--color-text-muted);
}

.reminder__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.reminder__when {
  font-weight: 600;
  color: var(--color-text-secondary);
}

.reminder[data-state='due'] .reminder__when {
  color: var(--color-error);
}

.reminder__issue {
  font-weight: 600;
  color: var(--color-primary);
}

.reminder__ack {
  flex-shrink: 0;
  padding: 3px 8px;
  border: 1px solid var(--color-success-border);
  border-radius: var(--radius-md);
  background: none;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-success);
}
</style>
