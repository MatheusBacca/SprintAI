<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ShieldCheck } from 'lucide-vue-next'
import BitbucketConnectionForm from '@/components/settings/BitbucketConnectionForm.vue'
import ConnectionCard from '@/components/settings/ConnectionCard.vue'
import JiraConnectionForm from '@/components/settings/JiraConnectionForm.vue'
import ProgressStagesPanel from '@/components/settings/ProgressStagesPanel.vue'
import ShortcutsPanel from '@/components/settings/ShortcutsPanel.vue'
import SyncSettingsPanel from '@/components/settings/SyncSettingsPanel.vue'
import { useConnectionsStore } from '@/stores/connections'

const store = useConnectionsStore()
const route = useRoute()
const router = useRouter()

const tabs = [
  { id: 'conexoes', label: 'Conexões' },
  { id: 'sincronizacao', label: 'Sincronização' },
  { id: 'progresso', label: 'Progresso' },
  { id: 'atalhos', label: 'Atalhos' },
]

const activeTab = computed(() => {
  const requested = tabs.find((t) => t.id === route.query.aba && !t.delivery)
  return requested?.id ?? 'conexoes'
})

function selectTab(tab) {
  if (!tab.delivery) router.replace({ query: { ...route.query, aba: tab.id } })
}

onMounted(() => store.load())
</script>

<template>
  <section class="settings">
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
    <ProgressStagesPanel v-else-if="activeTab === 'progresso'" />
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
