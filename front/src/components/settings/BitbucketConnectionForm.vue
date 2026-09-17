<script setup>
import { reactive, watch } from 'vue'
import ConnectionCard from './ConnectionCard.vue'
import { useConnectionsStore } from '@/stores/connections'

const TOKEN_URL = 'https://id.atlassian.com/manage-profile/security/api-tokens'
const SCOPES = 'read:user:bitbucket, read:repository:bitbucket, read:pullrequest:bitbucket'

const store = useConnectionsStore()

const form = reactive({
  email: '',
  workspace: 'weonrepo',
  api_token: '',
})

watch(
  () => store.bitbucket.settings,
  (settings) => {
    if (settings?.email) form.email = settings.email
    if (settings?.workspace) form.workspace = settings.workspace
  },
  { immediate: true },
)

async function submit() {
  const ok = await store.save('bitbucket', { ...form, api_token: form.api_token || null })
  if (ok) form.api_token = ''
}
</script>

<template>
  <ConnectionCard
    title="Bitbucket"
    description="Branches e pull requests vinculados às tarefas pela chave (WAI-XXXX) no nome da branch."
    :status="store.bitbucket"
    :busy="store.busy.bitbucket"
    :feedback="store.feedback.bitbucket"
    :help-url="TOKEN_URL"
    help-label="Criar token de API com escopos (Bitbucket)"
    @submit="submit"
    @test="store.test('bitbucket')"
    @remove="store.remove('bitbucket')"
  >
    <div class="field-row">
      <label class="field">
        <span class="field__label">E-mail da conta Atlassian</span>
        <input v-model.trim="form.email" class="field__input" type="email" required autocomplete="username">
      </label>
      <label class="field">
        <span class="field__label">Workspace</span>
        <input v-model.trim="form.workspace" class="field__input" type="text" required spellcheck="false">
      </label>
    </div>

    <label class="field">
      <span class="field__label">Token de API</span>
      <input
        v-model="form.api_token"
        class="field__input"
        type="password"
        autocomplete="new-password"
        spellcheck="false"
        :required="!store.bitbucket.configured"
        :placeholder="store.bitbucket.configured ? 'Salvo no Cofre do Windows — deixe em branco para manter' : 'Cole o token aqui'"
      >
      <span class="field__hint">Escopos: {{ SCOPES }}</span>
    </label>
  </ConnectionCard>
</template>
