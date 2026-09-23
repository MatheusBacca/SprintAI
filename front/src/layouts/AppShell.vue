<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'
import AppSidebar from '@/components/shell/AppSidebar.vue'
import ContextEditor from '@/components/contexts/ContextEditor.vue'
import ContextResolveDialog from '@/components/contexts/ContextResolveDialog.vue'
import AppTopbar from '@/components/shell/AppTopbar.vue'
import GlobalShortcuts from '@/components/shell/GlobalShortcuts.vue'
import GlobalSearch from '@/components/search/GlobalSearch.vue'
import JiraActionPopover from '@/components/jira/JiraActionPopover.vue'
import NoteEditor from '@/components/notes/NoteEditor.vue'
import ReminderPalette from '@/components/notes/ReminderPalette.vue'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { useNotesStore } from '@/stores/notes'
import { useNotificationsStore } from '@/stores/notifications'
import { useRealtimeStore } from '@/stores/realtime'
import { useRefreshStore } from '@/stores/refresh'
import { useSyncStore } from '@/stores/sync'

const jiraActions = useJiraActionsStore()
const notes = useNotesStore()
const notifications = useNotificationsStore()
const realtime = useRealtimeStore()
const refresh = useRefreshStore()
const sync = useSyncStore()

// O stream é do app, não de uma tela: antes ele só vivia na Home, e quem estava na
// Semana ou com o painel da tarefa aberto não ficava sabendo de sync nenhum.
onMounted(() => {
  realtime.connect()
  notifications.startPolling()
})
onBeforeUnmount(() => {
  realtime.disconnect()
  notifications.stopPolling()
})

// Salvou/adiou/concluiu um lembrete em qualquer tela: o sino reavalia na hora,
// sem esperar o ciclo.
watch(() => notes.revision, () => notifications.poll())

// O sino também mostra dado do espelho (as mexidas nas tarefas da sprint ativa): sync
// terminado ou Recarregar refaz a lista junto com as telas.
watch(() => refresh.revision, () => notifications.poll())

// Duas fontes para o mesmo fato — o `refresh` desempata pelo id da execução.
watch(
  () => realtime.revisionOf('sync.finished'),
  (count) => count && refresh.afterSync(realtime.events['sync.finished']?.payload?.id ?? null),
)
watch(
  () => sync.status?.last_run?.id,
  (id, previous) => previous && id !== previous && refresh.afterSync(id),
)

// Status ou SP mudado pelo SprintAI: o espelho já tem o valor novo, então tudo que está
// aberto se refaz. A resposta chega na aba que escreveu; o stream avisa as outras — e a
// que escreveu também, desempatado pelo id da escrita.
watch(
  () => jiraActions.lastWrite?.id,
  (id) => id && refresh.afterWrite(id),
)
watch(
  () => realtime.revisionOf('issue.changed'),
  (count) => count && refresh.afterWrite(realtime.events['issue.changed']?.payload?.write_id ?? null),
)
</script>

<template>
  <div class="shell">
    <AppSidebar />
    <div class="shell__main">
      <AppTopbar />
      <main class="shell__content">
        <slot />
      </main>
    </div>
    <!-- Uma instância para o app todo: qualquer tela abre o editor pelo store -->
    <NoteEditor />
    <ContextEditor />
    <ContextResolveDialog />
    <ReminderPalette />
    <GlobalSearch />
    <GlobalShortcuts />
    <JiraActionPopover />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100%;
}

.shell__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.shell__content {
  flex: 1;
  overflow: auto;
  padding: var(--space-5);
}
</style>
