<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'
import { useSyncStore } from '@/stores/sync'
import { formatRelative } from '@/utils/time'

const sync = useSyncStore()

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

const title = computed(() => {
  if (sync.statusError) return sync.statusError
  const errors = sync.lastRun?.errors ?? []
  if (errors.length) return errors.map((e) => e.message).join('\n')
  return 'Clique para sincronizar agora'
})
</script>

<template>
  <button
    type="button"
    class="sync"
    :class="`sync--${state}`"
    :title="title"
    :disabled="sync.running || sync.triggering || state === 'offline'"
    @click="sync.trigger()"
  >
    <AlertTriangle v-if="state === 'warning'" :size="14" />
    <RefreshCw v-else :size="14" :class="{ 'sync__spin': state === 'running' }" />
    <span>{{ label }}</span>
  </button>
</template>

<style scoped>
.sync {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
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

.sync__spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
