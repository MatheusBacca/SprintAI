<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { CheckCheck } from 'lucide-vue-next'
import { useConcludeSettingsStore } from '@/stores/concludeSettings'

/**
 * Configurações › Concluir: o que o botão "Concluir" dos cards faz em cada repositório. Um
 * repo pode levar a tarefa direto a "Concluído"; outro, mergear o PR e levar a "DISPONIVEL
 * PARA TESTES". Repo sem status e sem merge fica sem o botão.
 *
 * O status é texto (com os do espelho como sugestão) e é conferido na hora do Concluir
 * contra as transições que o Jira oferece — um nome que o workflow não tem aparece no plano
 * como "o Jira não oferece".
 */
const store = useConcludeSettingsStore()

const STRATEGIES = [
  { id: 'merge_commit', label: 'Merge commit' },
  { id: 'squash', label: 'Squash' },
  { id: 'fast_forward', label: 'Fast-forward' },
]

const blank = () => ({ jira_status: '', merge: false, strategy: 'merge_commit', close_source_branch: true })
const draft = ref(null)

function reset() {
  draft.value = Object.fromEntries(
    store.knownRepos.map((slug) => [slug, { ...blank(), ...store.repos[slug], jira_status: store.repos[slug]?.jira_status ?? '' }]),
  )
}

onMounted(async () => {
  await store.load()
  reset()
})
watch(() => store.repos, reset)

const payload = computed(() =>
  Object.fromEntries(
    Object.entries(draft.value ?? {})
      .map(([slug, rule]) => [slug, { ...rule, jira_status: rule.jira_status.trim() || null }])
      .filter(([, rule]) => rule.jira_status || rule.merge),
  ),
)

const dirty = computed(() => draft.value !== null && JSON.stringify(payload.value) !== JSON.stringify(sorted(store.repos)))

function sorted(repos) {
  return Object.fromEntries(Object.keys(repos).sort().map((slug) => [slug, repos[slug]]))
}

function summary(rule) {
  const parts = []
  if (rule.merge) parts.push(`mergeia (${STRATEGIES.find((s) => s.id === rule.strategy)?.label.toLowerCase()})`)
  if (rule.jira_status.trim()) parts.push(`leva a “${rule.jira_status.trim()}”`)
  return parts.length ? parts.join(' e ') : 'sem Concluir'
}

async function save() {
  await store.save(payload.value)
}
</script>

<template>
  <section class="conclude-settings card">
    <header class="conclude-settings__header">
      <CheckCheck :size="18" />
      <div>
        <h2 class="conclude-settings__title">O que o "Concluir" faz em cada repositório</h2>
        <p class="conclude-settings__desc">
          O botão <strong>Concluir</strong> aparece no card (à direita do selo do PR) quando o repo da tarefa tem uma
          receita aqui e o card está apto: o PR aprovado pela regra de Configurações › Pull requests e a tarefa
          ainda antes de testes. Ao clicar, o plano mostra o que vai acontecer e nada roda antes da confirmação. O
          merge vem primeiro; o Jira só anda se ele entrou. Mergear pede um token do Bitbucket com o escopo
          <code>write:pullrequest:bitbucket</code> (Configurações › Conexões).
        </p>
      </div>
    </header>

    <p v-if="store.error" class="conclude-settings__error" role="alert">{{ store.error }}</p>
    <p v-else-if="draft === null" class="conclude-settings__muted">Carregando…</p>
    <p v-else-if="!store.knownRepos.length" class="conclude-settings__muted">
      Nenhum repositório escolhido em Sincronização — é de lá que vêm os repos desta lista.
    </p>

    <template v-else>
      <datalist id="conclude-statuses">
        <option v-for="status in store.statuses" :key="status" :value="status" />
      </datalist>

      <table class="conclude-settings__table">
        <thead>
          <tr>
            <th scope="col">Repositório</th>
            <th scope="col">Status no Jira</th>
            <th scope="col">Merge do PR</th>
            <th scope="col">Estratégia</th>
            <th scope="col">Branch de origem</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="slug in store.knownRepos" :key="slug" :data-repo="slug" :data-active="payload[slug] ? true : null">
            <th scope="row">
              <span class="conclude-settings__repo">{{ slug }}</span>
              <span class="conclude-settings__summary">{{ summary(draft[slug]) }}</span>
            </th>
            <td>
              <input
                v-model="draft[slug].jira_status"
                type="text"
                list="conclude-statuses"
                class="field__input conclude-settings__status"
                maxlength="80"
                placeholder="não mexe no Jira"
                :aria-label="`Status do Jira no Concluir de ${slug}`"
              >
            </td>
            <td>
              <label class="conclude-settings__check">
                <input v-model="draft[slug].merge" type="checkbox" :aria-label="`Mergear o PR no Concluir de ${slug}`">
                mergear
              </label>
            </td>
            <td>
              <select
                v-model="draft[slug].strategy"
                class="field__input conclude-settings__select"
                :disabled="!draft[slug].merge"
                :aria-label="`Estratégia de merge de ${slug}`"
              >
                <option v-for="strategy in STRATEGIES" :key="strategy.id" :value="strategy.id">{{ strategy.label }}</option>
              </select>
            </td>
            <td>
              <label class="conclude-settings__check">
                <input
                  v-model="draft[slug].close_source_branch"
                  type="checkbox"
                  :disabled="!draft[slug].merge"
                  :aria-label="`Fechar a branch de origem no merge de ${slug}`"
                >
                fechar
              </label>
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="conclude-settings__footer">
        <p v-if="store.feedback" class="conclude-settings__feedback" :data-type="store.feedback.type" role="status">
          {{ store.feedback.text }}
        </p>
        <button type="button" class="btn btn--secondary" :disabled="!dirty || store.saving" @click="reset">Descartar</button>
        <button type="button" class="btn btn--primary" :disabled="!dirty || store.saving" @click="save">
          {{ store.saving ? 'Salvando…' : 'Salvar receitas' }}
        </button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.conclude-settings {
  max-width: 980px;
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.conclude-settings__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

.conclude-settings__header > svg {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--color-primary);
}

.conclude-settings__title {
  margin: 0 0 4px;
  font-size: var(--text-md);
  font-weight: 600;
}

.conclude-settings__desc,
.conclude-settings__muted {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.conclude-settings__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.conclude-settings__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.conclude-settings__table th,
.conclude-settings__table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: middle;
}

.conclude-settings__table thead th {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
}

.conclude-settings__table tbody th {
  font-weight: 500;
}

.conclude-settings__table tr[data-active] th {
  box-shadow: inset 3px 0 0 var(--color-success-text);
}

.conclude-settings__repo {
  display: block;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.conclude-settings__summary {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-muted);
}

.conclude-settings__status {
  width: 100%;
  min-width: 200px;
  padding: 4px 8px;
}

.conclude-settings__select {
  padding: 4px 8px;
}

.conclude-settings__check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.conclude-settings__footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: var(--space-2);
}

.conclude-settings__feedback {
  margin: 0 auto 0 0;
  font-size: var(--text-sm);
}

.conclude-settings__feedback[data-type='success'] {
  color: var(--color-success-text);
}

.conclude-settings__feedback[data-type='error'] {
  color: var(--color-error);
}
</style>
