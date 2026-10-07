<script setup>
import { computed, ref, watch } from 'vue'
import { AlertTriangle, Check, ExternalLink, GitMerge, Hourglass, LoaderCircle, MoveRight, X } from 'lucide-vue-next'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { safeUrl } from '@/utils/safeUrl'

/**
 * O plano do "Concluir", dentro do painel único: é a proposta. Nada roda até o
 * "Confirmar e concluir" — proposta → confirmação → ação, como toda escrita do SprintAI.
 *
 * O merge vem primeiro e o Jira só anda se todos os merges entraram; o back confere de novo
 * contra o plano de agora antes de rodar. Tarefa com vários PRs conclui por partes: entram os
 * aprovados, os outros ficam listados, e o Jira espera o Concluir do último. Os avisos (rascunho, aprovações, build) não barram:
 * quem barra é o Bitbucket, pelas merge checks. Depois de rodar, o painel fica com o
 * resultado de cada passo — inclusive o que falhou, com o link do PR.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
})

const store = useJiraActionsStore()
const STRATEGY = { merge_commit: 'merge commit', squash: 'squash', fast_forward: 'fast-forward' }

const plan = computed(() => (store.conclude.key === props.issueKey ? store.conclude.data : null))
const result = computed(() => (store.conclude.key === props.issueKey ? store.conclude.result : null))
const chosen = ref(null)

// Um status só: é ele. Mais de um (repos com receitas diferentes): o dev escolhe.
watch(
  plan,
  (value) => {
    const targets = value?.targets ?? []
    chosen.value = targets.length === 1 ? targets[0].status : null
  },
  { immediate: true },
)

const target = computed(() => plan.value?.targets.find((t) => t.status === chosen.value) ?? null)
const needsChoice = computed(() => (plan.value?.targets.length ?? 0) > 1 && !chosen.value)
const nothingToDo = computed(() => plan.value && !plan.value.merges.length && !plan.value.targets.length)
// PRs abertos que este Concluir não mergeia: o passo do Jira fica para o último.
const waiting = computed(() => plan.value?.waiting ?? [])
const held = computed(() => plan.value?.held_statuses ?? [])
const holding = computed(() => result.value?.steps.some((step) => step.kind === 'hold') ?? false)
const blocked = computed(() => {
  // Card que deixou de estar apto (o PR perdeu a aprovação, a tarefa andou para testes).
  if (!plan.value || plan.value.blocked || nothingToDo.value || needsChoice.value) return true
  if (target.value && !target.value.available) return true
  // Já no status e sem merge: não há o que fazer.
  return !plan.value.merges.length && Boolean(target.value?.current)
})

function confirm() {
  if (blocked.value || store.saving) return
  store.runConclude(props.issueKey, {
    jira_status: chosen.value,
    merges: plan.value.merges.map((m) => ({ repo_slug: m.repo_slug, pr_id: m.pr_id })),
  })
}
</script>

<template>
  <div class="conclude">
    <header class="conclude__head">
      <strong class="conclude__title">Concluir {{ issueKey }}</strong>
      <span v-if="plan" class="conclude__status" title="Status no Jira agora">{{ plan.status }}</span>
    </header>

    <p v-if="store.conclude.loading" class="conclude__muted"><LoaderCircle :size="13" class="spin" /> Lendo os PRs e o Jira…</p>
    <p v-else-if="store.conclude.error" class="conclude__error" role="alert">{{ store.conclude.error }}</p>

    <template v-else-if="result">
      <ol class="conclude__steps">
        <li v-for="(step, index) in result.steps" :key="index" class="conclude__step" :data-ok="step.ok" :data-kind="step.kind">
          <Hourglass v-if="step.kind === 'hold'" :size="14" class="conclude__icon" />
          <Check v-else-if="step.ok" :size="14" class="conclude__icon" />
          <X v-else :size="14" class="conclude__icon" />
          <span class="conclude__step-text">
            <span>{{ step.label }}</span>
            <span v-if="step.message" class="conclude__step-note">{{ step.message }}</span>
          </span>
          <a v-if="safeUrl(step.url)" :href="safeUrl(step.url)" target="_blank" rel="noopener noreferrer" class="conclude__link" title="Abrir o PR no Bitbucket">
            <ExternalLink :size="12" />
          </a>
        </li>
      </ol>
      <p class="conclude__muted">
        <template v-if="!result.done">Parou no passo que falhou — o que vinha depois não rodou.</template>
        <template v-else-if="holding">Mergeado. O Jira fica onde está até o último PR da tarefa entrar.</template>
        <template v-else>Concluída. O selo do PR muda quando o sync, que já foi chamado, terminar.</template>
      </p>
      <button type="button" class="btn btn--secondary conclude__close" @click="store.close()">Fechar</button>
    </template>

    <template v-else-if="plan">
      <p v-if="plan.blocked" class="conclude__error" role="alert">{{ plan.blocked }}</p>
      <p v-if="nothingToDo" class="conclude__muted">Nada a fazer para esta tarefa agora.</p>

      <ol v-else class="conclude__steps">
        <li v-for="merge in plan.merges" :key="`${merge.repo_slug}:${merge.pr_id}`" class="conclude__step conclude__step--merge">
          <GitMerge :size="14" class="conclude__icon" />
          <span class="conclude__step-text">
            <span>Mergear o PR #{{ merge.pr_id }} em <strong>{{ merge.repo_slug }}</strong></span>
            <span class="conclude__step-note">
              <code>{{ merge.source_branch }}</code> → <code>{{ merge.destination_branch }}</code>
              · {{ STRATEGY[merge.strategy] }} · {{ merge.close_source_branch ? 'fecha a branch' : 'mantém a branch' }}
            </span>
            <span v-for="warning in merge.warnings" :key="warning" class="conclude__warning">
              <AlertTriangle :size="11" /> {{ warning }}
            </span>
          </span>
          <a v-if="safeUrl(merge.url)" :href="safeUrl(merge.url)" target="_blank" rel="noopener noreferrer" class="conclude__link" title="Abrir o PR no Bitbucket">
            <ExternalLink :size="12" />
          </a>
        </li>

        <li v-if="plan.targets.length === 1" class="conclude__step" :data-blocked="!target?.available || null">
          <MoveRight :size="14" class="conclude__icon" />
          <span class="conclude__step-text">
            <span v-if="target.current">Já está em <strong>{{ target.status }}</strong> no Jira</span>
            <span v-else>Mover para <strong>{{ target.status }}</strong> no Jira</span>
            <span v-if="target.reason" class="conclude__step-note conclude__step-note--error">{{ target.reason }}</span>
            <span v-else-if="plan.merges.length && !target.current" class="conclude__step-note">só depois que o merge entrar</span>
          </span>
        </li>
        <li v-else-if="held.length" class="conclude__step conclude__step--held">
          <Hourglass :size="14" class="conclude__icon" />
          <span class="conclude__step-text">
            <span>Mover para <strong>{{ held.join(' ou ') }}</strong> no Jira <em>fica para o último PR</em></span>
            <span class="conclude__step-note">Ainda aberto{{ waiting.length > 1 ? 's' : '' }}:</span>
            <span v-for="pr in waiting" :key="`${pr.repo_slug}:${pr.pr_id}`" class="conclude__waiting">
              <a v-if="safeUrl(pr.url)" :href="safeUrl(pr.url)" target="_blank" rel="noopener noreferrer" title="Abrir o PR no Bitbucket">#{{ pr.pr_id }}</a>
              <template v-else>#{{ pr.pr_id }}</template>
              em {{ pr.repo_slug }} — {{ pr.reason }}
            </span>
          </span>
        </li>
        <li v-else-if="plan.targets.length > 1" class="conclude__step">
          <MoveRight :size="14" class="conclude__icon" />
          <fieldset class="conclude__choice">
            <legend>Os repos da tarefa levam a status diferentes — para qual ela vai?</legend>
            <label v-for="option in plan.targets" :key="option.status" :data-blocked="!option.available || null" :title="option.reason ?? ''">
              <input v-model="chosen" type="radio" name="conclude-target" :value="option.status" :disabled="!option.available">
              {{ option.status }}<template v-if="option.current"> (atual)</template>
            </label>
          </fieldset>
        </li>
      </ol>

      <p v-for="note in plan.notes" :key="note" class="conclude__muted">{{ note }}</p>

      <p v-if="store.error" class="conclude__error" role="alert">{{ store.error }}</p>
      <button type="button" class="btn btn--primary conclude__confirm" :disabled="blocked || store.saving" @click="confirm">
        <LoaderCircle v-if="store.saving" :size="13" class="spin" />
        Confirmar e concluir
      </button>
    </template>
  </div>
</template>

<style scoped>
.conclude {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 340px;
}

.conclude__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}

.conclude__title {
  font-size: var(--text-sm);
}

.conclude__status {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.conclude__muted {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.conclude__error {
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  font-size: var(--text-xs);
  color: var(--color-error);
}

.conclude__steps {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.conclude__step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
}

.conclude__step--held em {
  font-style: normal;
  color: var(--color-text-muted);
}

.conclude__waiting {
  color: var(--color-text-secondary);
  overflow-wrap: anywhere;
}

.conclude__waiting a {
  color: var(--color-primary);
}

.conclude__step[data-blocked] {
  border-color: var(--color-error);
}

.conclude__step[data-ok='true'] .conclude__icon {
  color: var(--color-success-text);
}

.conclude__step[data-ok='false'] {
  border-color: var(--color-error);
}

.conclude__step[data-ok='false'] .conclude__icon {
  color: var(--color-error);
}

/* Depois do `data-ok`: o passo em espera é "ok", mas não é verde — o Jira não andou. */
.conclude__step--held .conclude__icon,
.conclude__step[data-kind='hold'] .conclude__icon {
  color: var(--color-warning-text);
}

.conclude__icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--color-primary);
}

.conclude__step-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conclude__step-note {
  color: var(--color-text-muted);
  overflow-wrap: anywhere;
}

.conclude__step-note code {
  font-family: var(--font-mono);
  font-size: 11px;
}

.conclude__step-note--error {
  color: var(--color-error);
}

.conclude__warning {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-warning-text);
}

.conclude__link {
  flex-shrink: 0;
  color: var(--color-text-muted);
}

.conclude__link:hover {
  color: var(--color-primary);
}

.conclude__choice {
  flex: 1;
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.conclude__choice legend {
  margin-bottom: 4px;
  color: var(--color-text-secondary);
}

.conclude__choice label[data-blocked] {
  color: var(--color-text-muted);
}

.conclude__confirm,
.conclude__close {
  align-self: flex-end;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
