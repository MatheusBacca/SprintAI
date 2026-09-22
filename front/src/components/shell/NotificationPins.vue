<script setup>
import { PinOff } from 'lucide-vue-next'
import { useNotificationsStore } from '@/stores/notifications'
import { formatDateTime } from '@/utils/datetime'

/**
 * As notificações que o dev fixou, no topo de toda tela — só o título. Clicar abre
 * a modal do lembrete, que é onde dá para mexer no texto, no horário e concluir.
 */
const store = useNotificationsStore()

function title(note) {
  return note.title || (note.body || '').slice(0, 60)
}
</script>

<template>
  <ul v-if="store.pinned.length" class="pins" aria-label="Notificações fixadas">
    <li v-for="note in store.pinned" :key="note.id" class="pins__item" :data-id="note.id">
      <button
        type="button"
        class="pins__open"
        :title="`${title(note)} — ${formatDateTime(note.remind_at)}`"
        @click="store.openNote(note)"
      >
        {{ title(note) }}
      </button>
      <button type="button" class="pins__off" title="Desafixar" @click="store.togglePin(note.id)">
        <PinOff :size="12" />
      </button>
    </li>
  </ul>
</template>

<style scoped>
.pins {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: hidden;
}

.pins__item {
  display: flex;
  align-items: center;
  min-width: 0;
  border: 1px solid var(--note-yellow-border);
  border-radius: var(--radius-md);
  background: var(--note-yellow-bg);
}

.pins__open {
  max-width: 220px;
  overflow: hidden;
  padding: 4px 2px 4px 10px;
  border: 0;
  background: none;
  color: var(--color-text);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pins__off {
  display: grid;
  place-items: center;
  width: 20px;
  height: 22px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.pins__off:hover {
  color: var(--color-text);
}

/* Tela estreita: o título encolhe antes de sumir — o `title` conta o resto. */
@media (max-width: 1100px) {
  .pins__open {
    max-width: 140px;
  }
}

/* Aqui até a busca vira só a lupa: o topo não comporta mais os fixados. */
@media (max-width: 760px) {
  .pins {
    display: none;
  }
}
</style>
