<script setup>
import { computed, reactive, watch } from 'vue'
import ConnectionCard from './ConnectionCard.vue'
import { useConnectionsStore } from '@/stores/connections'

const TOKEN_URL = 'https://id.atlassian.com/manage-profile/security/api-tokens'
/**
 * Tudo o que o SprintAI usa do Bitbucket — a mesma lista do `REQUIRED_SCOPES` do back, que o
 * teste de conexão confere contra os escopos que o próprio Bitbucket diz que o token tem.
 * Sem os três primeiros a conexão nem salva; sem os outros, salva e avisa o que não funciona.
 */
const SCOPES = [
  { scope: 'read:user:bitbucket', why: 'ler a sua conta' },
  { scope: 'read:repository:bitbucket', why: 'listar repositórios e branches' },
  { scope: 'read:pullrequest:bitbucket', why: 'espelhar PRs, comentários e builds' },
  { scope: 'read:workspace:bitbucket', why: 'listar os membros para escolher reviewer' },
  { scope: 'write:pullrequest:bitbucket', why: 'mergear no Concluir e mexer nos reviewers' },
]

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

/** O que o último teste viu faltar no token (vazio com o token completo). */
const missing = computed(() => {
  const names = store.bitbucket.settings?.missing_scopes ?? []
  return SCOPES.filter((item) => names.includes(item.scope))
})

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
      <span class="field__hint">
        Escopos do token (todos): <code class="scopes__list">{{ SCOPES.map((item) => item.scope).join(', ') }}</code>.
        Ao salvar e no Testar, o SprintAI confere no Bitbucket quais o token tem.
      </span>
    </label>

    <div v-if="missing.length" class="scopes__missing" role="alert">
      <strong>Faltam escopos no token salvo:</strong>
      <ul>
        <li v-for="item in missing" :key="item.scope"><code>{{ item.scope }}</code> — {{ item.why }}</li>
      </ul>
    </div>
  </ConnectionCard>
</template>

<style scoped>
.scopes__list {
  font-family: var(--font-mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.scopes__missing {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
  font-size: var(--text-xs);
}

.scopes__missing ul {
  margin: 4px 0 0;
  padding-left: var(--space-4);
}
</style>
