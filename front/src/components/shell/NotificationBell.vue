<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Bell, Pin, PinOff } from 'lucide-vue-next'
import { useNotificationsStore } from '@/stores/notifications'
import { formatDateTime } from '@/utils/datetime'

const store = useNotificationsStore()
const root = ref(null)

const label = computed(() =>
  store.unseenCount
    ? `Notificações (${store.unseenCount} a ver)`
    : `Notificações (${store.items.length})`,
)

function title(note) {
  return note.title || (note.body || '').slice(0, 60)
}

/** Clique fora fecha: o painel fica ancorado no sino, não é um modal com scrim. */
function onDocumentPointerDown(event) {
  if (store.open && root.value && !root.value.contains(event.target)) store.closePanel()
}

function onKeydown(event) {
  if (event.key === 'Escape' && store.open) {
    store.closePanel()
    event.stopPropagation()
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="notif">
    <button
      type="button"
      class="notif__bell"
      :class="{ 'notif__bell--alert': store.unseenCount > 0 }"
      :title="label"
      :aria-label="label"
      :aria-expanded="store.open"
      @click="store.togglePanel()"
    >
      <Bell :size="16" />
      <span v-if="store.unseenCount" class="notif__badge" aria-hidden="true">{{ store.unseenCount }}</span>
    </button>

    <section v-if="store.open" class="notif__panel" aria-label="Notificações">
      <header class="notif__head">
        <strong>Notificações</strong>
        <span class="notif__count">{{ store.items.length }}</span>
      </header>

      <p v-if="!store.items.length" class="notif__empty">Nenhuma notificação agora.</p>

      <ul v-else class="notif__list">
        <li
          v-for="note in store.items"
          :key="note.id"
          class="notif__item"
          :data-id="note.id"
        >
          <div class="notif__top">
            <p class="notif__title">{{ title(note) }}</p>
            <button
              type="button"
              class="notif__pin"
              :class="{ 'notif__pin--on': store.isPinned(note.id) }"
              :title="store.isPinned(note.id) ? 'Desafixar do topo' : 'Fixar o título no topo'"
              :aria-pressed="store.isPinned(note.id)"
              @click="store.togglePin(note.id)"
            >
              <PinOff v-if="store.isPinned(note.id)" :size="14" />
              <Pin v-else :size="14" />
            </button>
          </div>
          <p class="notif__when">
            {{ formatDateTime(note.remind_at)
            }}<template v-if="note.issues.length"> · {{ note.issues.map((i) => i.key).join(', ') }}</template>
          </p>
          <div class="notif__actions">
            <button type="button" class="btn btn--secondary" @click="store.openNote(note)">Abrir</button>
            <button type="button" class="btn btn--secondary" @click="store.snooze(note.id, 10)">Adiar 10 min</button>
            <button type="button" class="btn btn--secondary" @click="store.snooze(note.id, 60)">1 h</button>
            <button type="button" class="btn btn--primary" @click="store.acknowledge(note.id)">Concluir</button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.notif {
  position: relative;
  flex-shrink: 0;
}

.notif__bell {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
}

.notif__bell:hover,
.notif__bell[aria-expanded='true'] {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.notif__bell--alert {
  color: var(--color-warning);
  border-color: var(--color-warning-border);
}

/*
 * Abaixo do sino, não no canto de cima: o topo do botão encosta na borda da
 * barra e o selo ficaria cortado.
 */
.notif__badge {
  position: absolute;
  bottom: -7px;
  left: 50%;
  transform: translateX(-50%);
  min-width: 16px;
  padding: 0 4px;
  border: 1px solid var(--color-surface);
  border-radius: 999px;
  background: var(--color-error);
  color: var(--color-on-primary);
  font-size: 10px;
  font-weight: 700;
  line-height: 14px;
  text-align: center;
}

.notif__panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: var(--z-drawer);
  width: min(380px, calc(100vw - 32px));
  max-height: min(70vh, 520px);
  overflow: auto;
  padding: var(--space-3);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.notif__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  font-size: var(--text-sm);
}

.notif__count {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-neutral-surface);
  color: var(--color-neutral-text);
  font-size: var(--text-xs);
}

.notif__empty {
  margin: 0;
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.notif__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.notif__item {
  padding: var(--space-3);
  border: 1px solid var(--note-yellow-border);
  border-left-width: 4px;
  border-radius: var(--radius-md);
  background: var(--note-yellow-bg);
}

.notif__top {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}

.notif__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.notif__pin {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.notif__pin:hover {
  background: var(--note-scrim);
  color: var(--color-text);
}

.notif__pin--on {
  color: var(--note-yellow-accent);
}

.notif__when {
  margin: 2px 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.notif__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.notif__actions .btn {
  padding: 4px 10px;
  font-size: var(--text-xs);
}
</style>
