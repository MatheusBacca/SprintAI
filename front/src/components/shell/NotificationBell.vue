<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Bell, Pin, PinOff } from 'lucide-vue-next'
import ActivityKindIcon from '@/components/activity/ActivityKindIcon.vue'
import { activityKindMeta, activityTab } from '@/constants/activityKinds'
import { useIssueNavigation } from '@/composables/useIssueNavigation'
import { NOTIFICATION_KINDS, useNotificationsStore } from '@/stores/notifications'
import { formatDateTime } from '@/utils/datetime'
import { formatRelative } from '@/utils/time'

const store = useNotificationsStore()
const { openIssueInSprint } = useIssueNavigation()
const root = ref(null)

const label = computed(() =>
  store.unseenCount
    ? `Notificações (${store.unseenCount} a ver)`
    : `Notificações (${store.entries.length})`,
)

// Filtro ligado escondendo tudo é diferente de caixa vazia: o texto tem de dizer qual é.
const filtering = computed(() => store.kinds.length > 0)

function title(note) {
  return note.title || (note.body || '').slice(0, 60)
}

/**
 * Notificação de tarefa leva ao canvas da sprint dela, com o card em foco e o painel
 * aberto na aba do evento — comentário abre em Histórico, PR em PRs.
 */
function openUpdate(update) {
  openIssueInSprint(update.key, update.sprint_id, activityTab(update.kind))
  store.closePanel()
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
        <span class="notif__count">{{ store.entries.length }}</span>
      </header>

      <!-- Ligar um tipo mostra só ele; desligar o último volta a mostrar todos. -->
      <div class="notif__filters" role="group" aria-label="Filtrar por tipo">
        <button
          v-for="kind in NOTIFICATION_KINDS"
          :key="kind.id"
          type="button"
          class="notif__chip"
          :class="{ 'notif__chip--on': store.kinds.includes(kind.id) }"
          :aria-pressed="store.kinds.includes(kind.id)"
          @click="store.toggleKind(kind.id)"
        >
          {{ kind.label }} <span class="notif__chip-count">{{ store.counts[kind.id] }}</span>
        </button>
      </div>

      <p v-if="!store.visible.length" class="notif__empty">
        {{ filtering ? 'Nada deste tipo agora.' : 'Nenhuma notificação agora.' }}
      </p>

      <ul v-else class="notif__list">
        <template v-for="entry in store.visible" :key="entry.id">
          <li v-if="entry.kind === 'reminder'" class="notif__item" :data-id="entry.note.id">
            <div class="notif__top">
              <p class="notif__title">{{ title(entry.note) }}</p>
              <button
                type="button"
                class="notif__pin"
                :class="{ 'notif__pin--on': store.isPinned(entry.id) }"
                :title="store.isPinned(entry.id) ? 'Desafixar do topo' : 'Fixar o título no topo'"
                :aria-pressed="store.isPinned(entry.id)"
                @click="store.togglePin(entry.id)"
              >
                <PinOff v-if="store.isPinned(entry.id)" :size="14" />
                <Pin v-else :size="14" />
              </button>
            </div>
            <p class="notif__when">
              {{ formatDateTime(entry.note.remind_at)
              }}<template v-if="entry.note.issues.length"> · {{ entry.note.issues.map((i) => i.key).join(', ') }}</template>
            </p>
            <div class="notif__actions">
              <button type="button" class="btn btn--secondary" @click="store.openNote(entry.note)">Abrir</button>
              <button type="button" class="btn btn--secondary" @click="store.snooze(entry.note.id, 10)">Adiar 10 min</button>
              <button type="button" class="btn btn--secondary" @click="store.snooze(entry.note.id, 60)">1 h</button>
              <button type="button" class="btn btn--primary" @click="store.acknowledge(entry.note.id)">Concluir</button>
            </div>
          </li>

          <li v-else class="notif__item notif__item--update" :data-key="entry.update.key">
            <div class="notif__top">
              <ActivityKindIcon :kind="entry.update.kind" :size="14" />
              <p class="notif__title">
                <strong class="notif__key">{{ entry.update.key }}</strong> {{ entry.update.summary }}
              </p>
            </div>
            <p class="notif__what">
              <span class="notif__actor">{{ entry.update.actor_name ?? 'Alguém' }}</span>
              {{ activityKindMeta(entry.update.kind).text }}
              <strong v-if="entry.update.title">{{ entry.update.title }}</strong>
            </p>
            <p class="notif__when">
              {{ formatRelative(entry.update.occurred_at) }} · {{ entry.update.sprint_name
              }}<template v-if="entry.update.event_count > 1"> · {{ entry.update.event_count }} novidades</template>
            </p>
            <div class="notif__actions">
              <button type="button" class="btn btn--secondary" @click="openUpdate(entry.update)">Abrir na sprint</button>
            </div>
          </li>
        </template>
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
  font-size: var(--text-sm);
}

.notif__count {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-neutral-surface);
  color: var(--color-neutral-text);
  font-size: var(--text-xs);
}

.notif__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: var(--space-2) 0;
}

.notif__chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.notif__chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.notif__chip--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.notif__chip-count {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
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

/* Mexida na tarefa não é post-it: sai do amarelo do lembrete para não se confundir
   com o que é cobrança de fazer alguma coisa. */
.notif__item--update {
  border-color: var(--color-border-strong);
  border-left-color: var(--color-primary);
  background: var(--color-surface-muted);
}

.notif__top {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}

.notif__item--update .notif__top {
  padding-top: 1px;
}

.notif__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.notif__key {
  color: var(--color-primary);
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

/* O valor do evento (status novo, trecho do comentário) quebra em vez de empurrar a
   linha, e para em duas linhas para o painel continuar escaneável. */
.notif__what {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  margin: 4px 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  overflow-wrap: anywhere;
}

.notif__actor {
  font-weight: 600;
  color: var(--color-text);
}

.notif__when {
  margin: 2px 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.notif__item--update .notif__when {
  color: var(--color-text-muted);
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
