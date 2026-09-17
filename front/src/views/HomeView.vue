<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshCw, Wifi, WifiOff } from 'lucide-vue-next'

import ActivityFeed from '@/components/home/ActivityFeed.vue'
import RelevantReminders from '@/components/home/RelevantReminders.vue'
import SetupChecklist from '@/components/home/SetupChecklist.vue'
import SprintProgress from '@/components/home/SprintProgress.vue'
import SprintTimeline from '@/components/home/SprintTimeline.vue'
import WeekPendingCard from '@/components/home/WeekPendingCard.vue'
import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import { useActivityStore } from '@/stores/activity'
import { useHomeStore } from '@/stores/home'
import { useNotesStore } from '@/stores/notes'
import { useRealtimeStore } from '@/stores/realtime'
import { useRefreshStore } from '@/stores/refresh'
import { useScreenContextStore } from '@/stores/screenContext'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const home = useHomeStore()
const activity = useActivityStore()
const realtime = useRealtimeStore()
const refresh = useRefreshStore()
const notes = useNotesStore()
const screen = useScreenContextStore()
const ui = useUiStore()

const issueKey = computed(() => route.query.tarefa ?? null)
const data = computed(() => home.data)

screen.enter('home')
onBeforeUnmount(() => screen.enter(null))
watch(issueKey, (key) => screen.focusIssue(key), { immediate: true })
watch(
  () => home.issueKeys,
  (keys) => screen.$patch({ visibleIssueKeys: keys }),
)

onMounted(() => {
  home.loadAll()
  activity.load()
})

// Stream (B11): cada tipo de evento recarrega só o que mudou.
watch(() => realtime.revisionOf('activity.new'), () => activity.load())
watch(() => realtime.revisionOf('progress.changed'), () => home.loadAll())
watch(() => realtime.revisionOf('note.changed'), () => home.load())
// Sync concluído ou "Recarregar": o shell avisa e a tela inteira se refaz.
watch(() => refresh.revision, () => {
  home.loadAll()
  activity.load()
})
// Rede de segurança quando o stream está fora do ar (lembrete salvo nesta aba).
watch(() => notes.revision, () => home.load())

function setQuery(patch) {
  const query = { ...route.query, ...patch }
  for (const key of Object.keys(query)) if (query[key] === null || query[key] === '') delete query[key]
  router.replace({ query })
}

function openIssue(key, tab = null) {
  ui.requestIssueTab(key, tab)
  setQuery({ tarefa: key })
}

// Recarrega a Home e, junto, o painel da tarefa que estiver aberto.
function reload() {
  refresh.reload()
}
</script>

<template>
  <div class="home-page">
    <section class="home">
      <header class="home__header">
        <div class="home__intro">
          <h1 class="home__title">Seu dia</h1>
          <p class="home__subtitle">Onde as sprints estão, o que está pendente e o que mudou.</p>
        </div>
        <span
          class="home__stream"
          :data-on="realtime.connected || null"
          :title="realtime.connected ? 'Tempo real ligado: mudanças aparecem sem recarregar' : (realtime.error ?? 'Sem tempo real — a tela atualiza ao recarregar')"
        >
          <Wifi v-if="realtime.connected" :size="13" />
          <WifiOff v-else :size="13" />
          {{ realtime.connected ? 'ao vivo' : 'sem stream' }}
        </span>
        <button type="button" class="btn btn--secondary home__reload" :disabled="home.loading" @click="reload">
          <RefreshCw :size="14" :class="{ spin: home.loading }" /> Recarregar
        </button>
      </header>

      <p v-if="home.error" class="home__error card" role="alert">{{ home.error }}</p>

      <p v-if="data && !data.filtered_by_assignee" class="home__warn">
        A conexão com o Jira não guardou seu accountId: as listas mostram todas as tarefas do
        espelho, não só as suas. Teste a conexão de novo em Configurações.
      </p>

      <SetupChecklist />

      <SprintProgress
        :sprints="home.sprints"
        :loading="home.loading"
        :selected-key="issueKey"
        @open="openIssue"
      />

      <div class="home__grid">
        <div class="home__col">
          <WeekPendingCard
            :pending="data?.pending"
            :today="data?.today"
            :selected-key="issueKey"
            @open="openIssue"
          />
          <RelevantReminders :reminders="data?.reminders ?? []" />
        </div>
        <div class="home__col">
          <ActivityFeed :today="data?.today" :selected-key="issueKey" @open="openIssue" />
        </div>
      </div>

      <SprintTimeline :timeline="home.timeline" :selected-key="issueKey" @open="openIssue">
        <template #actions>
          <label class="home__next">
            <input
              type="checkbox"
              :checked="home.includeNext"
              @change="home.setIncludeNext($event.target.checked)"
            >
            próxima sprint
          </label>
        </template>
      </SprintTimeline>
      <p v-if="home.timelineError" class="home__error card" role="alert">{{ home.timelineError }}</p>
    </section>

    <IssueDrawer
      v-if="issueKey"
      :issue-key="issueKey"
      @close="setQuery({ tarefa: null })"
      @open="(key) => setQuery({ tarefa: key })"
    />
  </div>
</template>

<style scoped>
.home-page {
  height: 100%;
  display: flex;
  gap: var(--space-4);
}

.home {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.home__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.home__intro {
  min-width: 0;
}

.home__title {
  margin: 0 0 var(--space-1);
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.home__subtitle {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.home__stream {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.home__stream[data-on] {
  background: var(--color-success-surface);
  color: var(--color-success);
}

.home__reload {
  padding: 6px 12px;
}

.home__error {
  margin: 0;
  padding: var(--space-4);
  color: var(--color-error);
}

.home__warn {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
  font-size: var(--text-sm);
}

.home__grid {
  display: grid;
  /* `min(...)` evita que a coluna mínima force rolagem horizontal na página
     quando a janela é mais estreita que ela. */
  grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr));
  gap: var(--space-4);
  align-items: start;
}

.home__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

.home__next {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
