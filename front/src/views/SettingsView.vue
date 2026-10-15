<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ShieldCheck } from 'lucide-vue-next'
import BitbucketConnectionForm from '@/components/settings/BitbucketConnectionForm.vue'
import CardColorsPanel from '@/components/settings/CardColorsPanel.vue'
import ConcludeSettingsPanel from '@/components/settings/ConcludeSettingsPanel.vue'
import ConnectionCard from '@/components/settings/ConnectionCard.vue'
import JiraConnectionForm from '@/components/settings/JiraConnectionForm.vue'
import PrApprovalPanel from '@/components/settings/PrApprovalPanel.vue'
import ProgressStagesPanel from '@/components/settings/ProgressStagesPanel.vue'
import ShortcutsPanel from '@/components/settings/ShortcutsPanel.vue'
import SyncSettingsPanel from '@/components/settings/SyncSettingsPanel.vue'
import WorkspaceReposPanel from '@/components/settings/WorkspaceReposPanel.vue'
import { useConnectionsStore } from '@/stores/connections'

const store = useConnectionsStore()
const route = useRoute()
const router = useRouter()

const tabs = [
  { id: 'conexoes', label: 'Conexões' },
  { id: 'sincronizacao', label: 'Sincronização' },
  { id: 'fluxo', label: 'Fluxo de trabalho' },
  { id: 'cores', label: 'Cores dos cards' },
  { id: 'workspace', label: 'Workspace' },
  { id: 'atalhos', label: 'Atalhos' },
]

/**
 * Progresso, Pull requests e Concluir são uma aba só: as três dizem o caminho da tarefa —
 * em que etapa cada status cai, quando o PR conta como aprovado e o que o Concluir faz
 * com ele —, e o Concluir depende das outras duas. Em abas separadas, mudar uma pedia ir
 * e voltar para conferir a outra. Link salvo de uma aba de antes (`?aba=concluir`) abre
 * esta, onde as três se veem juntas.
 */
const FLOW_SECTIONS = ['progresso', 'pull-requests', 'concluir']

const activeTab = computed(() => {
  if (FLOW_SECTIONS.includes(route.query.aba)) return 'fluxo'
  const requested = tabs.find((t) => t.id === route.query.aba && !t.delivery)
  return requested?.id ?? 'conexoes'
})

function selectTab(tab) {
  if (!tab.delivery) router.replace({ query: { ...route.query, aba: tab.id } })
}

onMounted(() => store.load())
</script>

<template>
  <section class="settings" :class="{ 'settings--wide': activeTab === 'fluxo' }">
    <header class="settings__header">
      <h1 class="settings__title">Configurações</h1>
      <nav class="settings__tabs" aria-label="Seções de configuração">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="settings__tab"
          :class="{ 'settings__tab--active': tab.id === activeTab }"
          :disabled="!!tab.delivery"
          :aria-current="tab.id === activeTab ? 'page' : undefined"
          :title="tab.delivery ? `Chega na entrega ${tab.delivery}` : undefined"
          @click="selectTab(tab)"
        >
          {{ tab.label }}
          <small v-if="tab.delivery">{{ tab.delivery }}</small>
        </button>
      </nav>
    </header>

    <SyncSettingsPanel v-if="activeTab === 'sincronizacao'" />
    <!-- Progresso à esquerda; à direita, o que acontece com o PR: quando ele conta como
         aprovado e, embaixo, o que o Concluir faz com ele. -->
    <div v-else-if="activeTab === 'fluxo'" class="flow">
      <div id="fluxo-progresso" class="flow__section flow__section--plain card">
        <ProgressStagesPanel />
      </div>
      <div class="flow__column">
        <div id="fluxo-pull-requests" class="flow__section">
          <PrApprovalPanel />
        </div>
        <div id="fluxo-concluir" class="flow__section">
          <ConcludeSettingsPanel />
        </div>
      </div>
    </div>
    <CardColorsPanel v-else-if="activeTab === 'cores'" />
    <WorkspaceReposPanel v-else-if="activeTab === 'workspace'" />
    <ShortcutsPanel v-else-if="activeTab === 'atalhos'" />

    <template v-else>
      <div class="settings__notice">
        <ShieldCheck :size="18" />
        <p>
          Os tokens ficam no <strong>Cofre do Windows</strong> (Gerenciador de Credenciais, serviço
          <code>sprintai</code>). Eles nunca voltam para esta tela, não vão para o banco e não aparecem
          em logs. Uma conexão só é salva depois de testada.
        </p>
      </div>

      <p v-if="store.loadError" class="settings__error" role="alert">{{ store.loadError }}</p>

      <div class="settings__grid">
        <JiraConnectionForm />
        <BitbucketConnectionForm />
        <ConnectionCard
          title="OpenAI"
          description="Chat da IA contextual. Chega no marco M4 — até lá o SprintAI não faz nenhuma chamada à OpenAI."
          disabled
        />
      </div>
    </template>
  </section>
</template>

<style scoped>
.settings {
  max-width: 1080px;
  margin: 0 auto;
}

/* Duas colunas de painéis que antes tinham a aba inteira: a tela abre mais. */
.settings--wide {
  max-width: 1360px;
}

.settings__header {
  margin-bottom: var(--space-4);
}

.settings__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.settings__tabs {
  display: flex;
  gap: var(--space-5);
  border-bottom: 1px solid var(--color-border);
}

.settings__tab {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0 10px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.settings__tab:disabled {
  cursor: default;
  color: var(--color-text-muted);
}

.settings__tab small {
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  font-size: 11px;
}

.settings__tab--active {
  border-bottom-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: 600;
}

.flow {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 6fr);
  gap: var(--space-4);
  align-items: start;
}

.flow__column {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

/* Cada painel tinha a largura de uma aba inteira; aqui ele ocupa a sua coluna. */
.flow__section {
  min-width: 0;
}

.flow__section > :deep(.card) {
  max-width: none;
}

@media (max-width: 1100px) {
  .flow {
    grid-template-columns: 1fr;
  }
}

/* O painel de Progresso não tem cartão próprio como os outros dois. */
.flow__section--plain {
  padding: var(--space-5);
}

.settings__notice {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-primary-shadow);
  border-radius: var(--radius-lg);
  background: var(--color-primary-soft);
  color: var(--color-text);
  font-size: var(--text-sm);
}

.settings__notice svg {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--color-primary);
}

.settings__notice p {
  margin: 0;
}

.settings__notice code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.settings__error {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
}

.settings__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: var(--space-4);
  align-items: start;
}

@media (max-width: 520px) {
  .settings__grid {
    grid-template-columns: 1fr;
  }
}
</style>
