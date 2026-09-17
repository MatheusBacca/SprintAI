<script setup>
import { computed, onMounted } from 'vue'
import { CheckCircle2, Circle } from 'lucide-vue-next'
import { useConnectionsStore } from '@/stores/connections'
import { useSyncStore } from '@/stores/sync'

const connections = useConnectionsStore()
const sync = useSyncStore()

onMounted(() => {
  connections.load()
  sync.loadScope().catch(() => {})
})

const steps = computed(() => [
  {
    id: 'jira',
    title: 'Conectar o Jira',
    done: connections.jira.configured && !connections.jira.last_error,
    to: '/configuracoes?aba=conexoes',
  },
  {
    id: 'bitbucket',
    title: 'Conectar o Bitbucket',
    done: connections.bitbucket.configured && !connections.bitbucket.last_error,
    to: '/configuracoes?aba=conexoes',
  },
  {
    id: 'repos',
    title: 'Escolher repositórios e escopo',
    done: sync.selectedRepos.length > 0,
    to: '/configuracoes?aba=sincronizacao',
  },
  {
    id: 'sync',
    title: 'Primeira sincronização',
    done: sync.status?.last_success_at != null,
    to: '/configuracoes?aba=sincronizacao',
  },
])

const doneCount = computed(() => steps.value.filter((s) => s.done).length)
const complete = computed(() => doneCount.value === steps.value.length)
</script>

<template>
  <article v-if="!complete" class="card setup">
    <header class="setup__header">
      <h2 class="setup__title">Configuração inicial</h2>
      <span class="setup__progress">{{ doneCount }}/{{ steps.length }}</span>
    </header>
    <ol class="setup__steps">
      <li v-for="step in steps" :key="step.id" :class="{ 'setup__step--done': step.done }">
        <CheckCircle2 v-if="step.done" :size="18" class="setup__icon setup__icon--done" />
        <Circle v-else :size="18" class="setup__icon" />
        <RouterLink v-if="!step.done" :to="step.to" class="setup__link">{{ step.title }}</RouterLink>
        <span v-else>{{ step.title }}</span>
      </li>
    </ol>
  </article>
</template>

<style scoped>
.setup {
  padding: var(--space-5);
}

.setup__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.setup__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.setup__progress {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.setup__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.setup__steps li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.setup__icon {
  color: var(--color-text-muted);
}

.setup__icon--done {
  color: var(--color-success);
}

.setup__step--done {
  color: var(--color-text-secondary);
}

.setup__link {
  color: var(--color-primary);
  font-weight: 500;
}
</style>
