<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Search, StickyNote } from 'lucide-vue-next'
import NotificationBell from './NotificationBell.vue'
import NotificationPins from './NotificationPins.vue'
import RepoIssuesMenu from './RepoIssuesMenu.vue'
import SyncIndicator from './SyncIndicator.vue'
import TopbarTip from './TopbarTip.vue'
import { useHealthStore } from '@/stores/health'
import { useNotesStore } from '@/stores/notes'
import { useSearchStore } from '@/stores/search'
import { useShortcutsStore } from '@/stores/shortcuts'
import { ariaShortcut } from '@/utils/shortcuts'

const HEALTH_INTERVAL_MS = 30_000

const route = useRoute()
const health = useHealthStore()
const notes = useNotesStore()
const shortcuts = useShortcutsStore()
const search = useSearchStore()

/** O "novo lembrete" não tem botão no topo: a dica do botão de lembretes ensina os dois. */
const reminderTips = computed(() => [
  { label: 'Buscar lembretes', combo: shortcuts.bindings.open_reminders },
  { label: 'Novo lembrete com a seleção', combo: shortcuts.bindings.new_reminder },
])

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

    <!-- À direita, cada controle mostra o atalho só na dica (hover ou Tab), não no botão. -->
    <TopbarTip
      class="topbar__search-tip"
      :lines="[{ label: 'Busca global', combo: shortcuts.bindings.global_search }]"
      detail="Tarefas, comentários, PRs, contextos e lembretes"
    >
      <button
        type="button"
        class="topbar__search"
        aria-label="Busca global"
        :aria-keyshortcuts="ariaShortcut(shortcuts.bindings.global_search)"
        @click="search.openSearch()"
      >
        <Search :size="16" />
        <span class="topbar__search-text">Buscar tarefas, lembretes…</span>
      </button>
    </TopbarTip>

    <TopbarTip :lines="reminderTips">
      <button
        type="button"
        class="topbar__notes"
        aria-label="Buscar lembretes"
        :aria-keyshortcuts="ariaShortcut(shortcuts.bindings.open_reminders)"
        @click="notes.openPalette()"
      >
        <StickyNote :size="16" />
      </button>
    </TopbarTip>

    <RepoIssuesMenu />

    <NotificationBell />

    <SyncIndicator v-if="health.level === 'ok'" />

    <TopbarTip :lines="[{ label: statusLabel }]">
      <div class="topbar__status" :class="`topbar__status--${health.level}`" role="status" :aria-label="statusLabel">
        <span class="topbar__dot" />
        <span class="topbar__status-text">{{ statusShort }}</span>
      </div>
    </TopbarTip>
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

/* A dica embrulha a busca: o encolher e o empurrar para a direita ficam nela. */
.topbar .topbar__search-tip {
  margin-left: auto;
  flex: 0 1 230px;
  min-width: 44px;
}

.topbar__search {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  min-width: 0;
  height: var(--topbar-control-height);
  padding: 0 12px;
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

.topbar__notes {
  display: grid;
  place-items: center;
  width: var(--topbar-control-height);
  height: var(--topbar-control-height);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-secondary);
}

.topbar__notes:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* Tela estreita: some o texto de apoio, ficam os ícones (a busca vira só a lupa). */
@media (max-width: 1100px) {
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
  display: flex;
  align-items: center;
  height: var(--topbar-control-height);
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
