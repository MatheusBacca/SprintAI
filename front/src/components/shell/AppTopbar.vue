<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search, StickyNote } from 'lucide-vue-next'
import NotificationBell from './NotificationBell.vue'
import NotificationPins from './NotificationPins.vue'
import SyncIndicator from './SyncIndicator.vue'
import { useHealthStore } from '@/stores/health'
import { useNotesStore } from '@/stores/notes'
import { useSearchStore } from '@/stores/search'
import { useShortcutsStore } from '@/stores/shortcuts'

const HEALTH_INTERVAL_MS = 30_000

const route = useRoute()
const health = useHealthStore()
const notes = useNotesStore()
const shortcuts = useShortcutsStore()
const search = useSearchStore()

const remindersTitle = computed(() => {
  const combo = shortcuts.bindings.open_reminders
  return combo ? `Buscar lembretes (${combo})` : 'Buscar lembretes'
})

const statusLabel = computed(
  () =>
    ({
      ok: 'API e banco conectados',
      degraded: 'Banco indisponível — suba o Docker (docker compose up -d db)',
      down: 'API local fora do ar',
      unknown: 'Verificando…',
    })[health.level],
)

const statusShort = computed(
  () => ({ ok: 'Online', degraded: 'Sem banco', down: 'Offline', unknown: '…' })[health.level],
)

let timer
onMounted(() => {
  health.check()
  timer = setInterval(() => health.check(), HEALTH_INTERVAL_MS)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <header class="topbar">
    <nav class="topbar__crumbs" aria-label="Breadcrumb">
      <span class="topbar__crumb">SprintAI</span>
      <span class="topbar__sep">›</span>
      <span class="topbar__crumb topbar__crumb--current">{{ route.meta.title }}</span>
    </nav>

    <NotificationPins />

    <button type="button" class="topbar__search" aria-label="Busca global" @click="search.openSearch()">
      <Search :size="16" />
      <span class="topbar__search-text">Buscar tarefas, contextos ou lembretes…</span>
      <kbd v-if="shortcuts.bindings.global_search">{{ shortcuts.bindings.global_search }}</kbd>
    </button>

    <button type="button" class="topbar__notes" :title="remindersTitle" :aria-label="remindersTitle" @click="notes.openPalette()">
      <StickyNote :size="16" />
      <kbd v-if="shortcuts.bindings.open_reminders">{{ shortcuts.bindings.open_reminders }}</kbd>
    </button>

    <NotificationBell />

    <SyncIndicator v-if="health.level === 'ok'" />

    <div
      class="topbar__status"
      :class="`topbar__status--${health.level}`"
      :title="statusLabel"
      role="status"
      :aria-label="statusLabel"
    >
      <span class="topbar__dot" />
      <span class="topbar__status-text">{{ statusShort }}</span>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  height: var(--topbar-height);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  min-width: 0;
  padding: 0 var(--space-5);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.topbar__crumbs {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.topbar__crumb--current {
  color: var(--color-text);
  font-weight: 600;
}

.topbar__sep {
  color: var(--color-text-muted);
}

.topbar__search {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 0 1 340px;
  min-width: 44px;
  padding: 8px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  background: var(--color-surface);
  font: inherit;
  text-align: left;
  cursor: text;
}

.topbar__search:hover {
  border-color: var(--color-primary);
}

.topbar__search-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
}

.topbar__search kbd {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-muted);
}

.topbar__notes {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.topbar__notes:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.topbar__notes kbd {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-muted);
}

/* Tela estreita: some o texto de apoio, ficam os ícones (a busca vira só a lupa). */
@media (max-width: 1100px) {
  .topbar__notes kbd,
  .topbar__search kbd,
  .topbar__status-text {
    display: none;
  }
}

@media (max-width: 760px) {
  .topbar__search-text {
    display: none;
  }
}

.topbar__status {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.topbar__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-muted);
}

.topbar__status--ok .topbar__dot {
  background: var(--color-success);
}

.topbar__status--degraded .topbar__dot {
  background: var(--color-warning);
}

.topbar__status--down .topbar__dot {
  background: var(--color-error);
}
</style>
