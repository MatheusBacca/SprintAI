<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'
import AppSidebar from '@/components/shell/AppSidebar.vue'
import ContextEditor from '@/components/contexts/ContextEditor.vue'
import ContextResolveDialog from '@/components/contexts/ContextResolveDialog.vue'
import AppTopbar from '@/components/shell/AppTopbar.vue'
import GlobalShortcuts from '@/components/shell/GlobalShortcuts.vue'
import GlobalSearch from '@/components/search/GlobalSearch.vue'
import NoteEditor from '@/components/notes/NoteEditor.vue'
import ReminderCenter from '@/components/notes/ReminderCenter.vue'
import ReminderPalette from '@/components/notes/ReminderPalette.vue'
import { useRealtimeStore } from '@/stores/realtime'
import { useRefreshStore } from '@/stores/refresh'
import { useSyncStore } from '@/stores/sync'

const realtime = useRealtimeStore()
const refresh = useRefreshStore()
const sync = useSyncStore()

// O stream é do app, não de uma tela: antes ele só vivia na Home, e quem estava na
// Semana ou com o painel da tarefa aberto não ficava sabendo de sync nenhum.
onMounted(() => realtime.connect())
onBeforeUnmount(() => realtime.disconnect())

// Duas fontes para o mesmo fato — o `refresh` desempata pelo id da execução.
watch(
  () => realtime.revisionOf('sync.finished'),
  (count) => count && refresh.afterSync(realtime.events['sync.finished']?.payload?.id ?? null),
)
watch(
  () => sync.status?.last_run?.id,
  (id, previous) => previous && id !== previous && refresh.afterSync(id),
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
    <ReminderCenter />
    <GlobalShortcuts />
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
