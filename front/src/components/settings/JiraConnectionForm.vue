<script setup>
import { reactive, watch } from 'vue'
import ConnectionCard from './ConnectionCard.vue'
import { useConnectionsStore } from '@/stores/connections'

const TOKEN_URL = 'https://id.atlassian.com/manage-profile/security/api-tokens'
const SCOPES = 'read:jira-work, read:jira-user, read:board-scope:jira-software, read:sprint:jira-software'
// Só para mover status e mudar Story Points pelo SprintAI; sem ele, o resto continua lendo.
const WRITE_SCOPE = 'write:jira-work'

const store = useConnectionsStore()

const form = reactive({
  site_url: 'https://weon.atlassian.net',
  email: '',
  auth_mode: 'classic',
  api_token: '',
})

// Preenche com o que já está salvo (sem token: ele nunca volta da API).
watch(
  () => store.jira.settings,
  (settings) => {
    if (settings?.site_url) form.site_url = settings.site_url
    if (settings?.email) form.email = settings.email
    if (settings?.auth_mode) form.auth_mode = settings.auth_mode
  },
  { immediate: true },
)

async function submit() {
  const ok = await store.save('jira', { ...form, api_token: form.api_token || null })
  if (ok) form.api_token = ''
}
</script>

<template>
  <ConnectionCard
    title="Jira"
    description="Sprints, tarefas, links e comentários dos boards sincronizados."
    :status="store.jira"
    :busy="store.busy.jira"
    :feedback="store.feedback.jira"
    :help-url="TOKEN_URL"
    help-label="Criar token de API na Atlassian"
    @submit="submit"
    @test="store.test('jira')"
    @remove="store.remove('jira')"
  >
    <div class="field-row">
      <label class="field">
        <span class="field__label">Site</span>
        <input v-model.trim="form.site_url" class="field__input" type="url" required placeholder="https://weon.atlassian.net">
      </label>
      <label class="field">
        <span class="field__label">E-mail da conta Atlassian</span>
        <input v-model.trim="form.email" class="field__input" type="email" required autocomplete="username">
      </label>
    </div>

    <label class="field">
      <span class="field__label">Tipo de token</span>
      <select v-model="form.auth_mode" class="field__input">
        <option value="classic">Token clássico (acesso da sua conta)</option>
        <option value="scoped">Token com escopos (recomendado)</option>
      </select>
      <span v-if="form.auth_mode === 'scoped'" class="field__hint">
        Escopos: {{ SCOPES }}. Para mover status e mudar Story Points pelo SprintAI, some {{ WRITE_SCOPE }}.
      </span>
    </label>

    <label class="field">
      <span class="field__label">Token de API</span>
      <input
        v-model="form.api_token"
        class="field__input"
        type="password"
        autocomplete="new-password"
        spellcheck="false"
        :required="!store.jira.configured"
        :placeholder="store.jira.configured ? 'Salvo no Cofre do Windows — deixe em branco para manter' : 'Cole o token aqui'"
      >
    </label>
  </ConnectionCard>
</template>
