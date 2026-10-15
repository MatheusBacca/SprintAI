<script setup>
import { PinOff } from 'lucide-vue-next'
import { useNotificationsStore } from '@/stores/notifications'
import { formatDateTime } from '@/utils/datetime'

/**
 * Os lembretes que o dev fixou, no topo de toda tela — só o título. Clicar abre a modal
 * do lembrete, que é onde dá para mexer no texto, no horário e concluir. Notificação de
 * tarefa não se fixa: ela é notícia, e o lugar de acompanhá-la é o canvas da sprint.
 */
const store = useNotificationsStore()

function title(note) {
  return note.title || (note.body || '').slice(0, 60)
}
</script>

<template>
  <ul v-if="store.pinned.length" class="pins" aria-label="Notificações fixadas">
    <li v-for="entry in store.pinned" :key="entry.id" class="pins__item" :data-id="entry.note.id">
      <button
        type="button"
        class="pins__open"
        :title="`${title(entry.note)} — ${formatDateTime(entry.note.remind_at)}`"
        @click="store.openNote(entry.note)"
      >
        {{ title(entry.note) }}
      </button>
      <button type="button" class="pins__off" title="Desafixar" @click="store.togglePin(entry.id)">
        <PinOff :size="14" />
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

/*
 * Mesma altura dos outros controles do topo, e o título e o pin dividem essa altura
 * inteira: antes o pin era um quadradinho de 22px num chip de 30, com ícone menor que a
 * letra, e parecia solto dentro do post-it.
 */
.pins__item {
  display: flex;
  align-items: stretch;
  height: var(--topbar-control-height);
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--note-yellow-border);
  border-radius: var(--radius-md);
  background: var(--note-yellow-bg);
}

.pins__open {
  max-width: 220px;
  overflow: hidden;
  padding: 0 6px 0 10px;
  border: 0;
  background: none;
  color: var(--color-text);
  font-size: var(--text-xs);
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pins__off {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: calc(var(--topbar-control-height) - 2px);
  padding: 0;
  border: 0;
  border-left: 1px solid var(--note-yellow-border);
  background: none;
  color: var(--note-yellow-accent);
}

.pins__open:hover,
.pins__off:hover {
  background: var(--note-scrim);
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
