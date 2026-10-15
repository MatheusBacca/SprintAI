<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'
import TopbarTip from './TopbarTip.vue'
import { useShortcutsStore } from '@/stores/shortcuts'
import { useSyncStore } from '@/stores/sync'
import { ariaShortcut } from '@/utils/shortcuts'
import { formatRelative } from '@/utils/time'

const sync = useSyncStore()
const shortcuts = useShortcutsStore()

// Força o "há X minutos" a andar mesmo sem novo status.
const now = ref(new Date())
let clock
onMounted(() => {
  sync.startPolling()
  clock = setInterval(() => (now.value = new Date()), 30_000)
})
onBeforeUnmount(() => {
  sync.stopPolling()
  clearInterval(clock)
})

const state = computed(() => {
  if (sync.statusError) return 'offline'
  if (sync.running) return 'running'
  const run = sync.lastRun
  if (!run) return 'never'
  return run.status === 'success' ? 'ok' : 'warning'
})

const label = computed(() => {
  const lastSuccess = formatRelative(sync.status?.last_success_at, now.value)
  return {
    offline: 'Sync indisponível',
    running: 'Sincronizando…',
    never: 'Nunca sincronizado',
    ok: `Sincronizado ${lastSuccess}`,
    warning: sync.lastRun?.status === 'partial' ? 'Sync parcial' : 'Sync falhou',
  }[state.value]
})

/**
 * Embaixo do atalho na dica: o estado (em tela estreita o botão fica só com o ícone) e o
 * porquê do aviso — o erro do status ou os do último sync.
 */
const detail = computed(() => {
  if (sync.statusError) return sync.statusError
  const errors = sync.lastRun?.errors ?? []
  return [label.value, ...errors.map((e) => e.message)].join('\n')
})
</script>

<template>
  <TopbarTip :lines="[{ label: 'Sincronizar agora', combo: shortcuts.bindings.sync_now }]" :detail="detail">
    <button
      type="button"
      class="sync"
      :class="`sync--${state}`"
      :aria-keyshortcuts="ariaShortcut(shortcuts.bindings.sync_now)"
      :disabled="sync.running || sync.triggering || state === 'offline'"
      @click="sync.trigger()"
    >
      <AlertTriangle v-if="state === 'warning'" :size="14" />
      <RefreshCw v-else :size="14" :class="{ 'sync__spin': state === 'running' }" />
      <span class="sync__label">{{ label }}</span>
    </button>
  </TopbarTip>
</template>

<style scoped>
.sync {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: var(--topbar-control-height);
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.sync:not(:disabled):hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.sync:disabled {
  cursor: default;
}

.sync--warning {
  border-color: var(--color-warning-border);
  color: var(--color-warning);
}

.sync--running {
  color: var(--color-primary);
}

/* Tela estreita: o topo não comporta o texto; o estado continua na dica. */
@media (max-width: 1100px) {
  .sync__label {
    display: none;
  }
}

.sync__spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
