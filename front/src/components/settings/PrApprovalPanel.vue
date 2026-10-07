<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { GitPullRequest } from 'lucide-vue-next'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { APPROVAL_RULES } from '@/constants/prStatus'
import { usePrApprovalStore } from '@/stores/prApproval'

/**
 * Configurações › Pull requests: quanto dos revisores precisa aprovar para o PR contar
 * como "Aprovada". A regra é aplicada no back — os exemplos abaixo só mostram, com a
 * regra escolhida e ainda não salva, como o badge fica.
 */
const store = usePrApprovalStore()

const draft = ref(null)

function reset() {
  draft.value = store.minPercent
}

onMounted(async () => {
  await store.load()
  reset()
})
watch(() => store.minPercent, reset)

const dirty = computed(() => draft.value !== null && draft.value !== store.minPercent)
const current = computed(() => APPROVAL_RULES.find((rule) => rule.percent === draft.value) ?? null)

// Mesma conta do `ApprovalRule.required` do back — aqui só para a prévia.
function required(reviewers) {
  return Math.max(1, Math.ceil((reviewers * draft.value) / 100))
}

const EXAMPLES = [
  { text: '2 revisores, 1 aprovou', approvals: 1, reviewers: 2, changes: 0 },
  { text: '3 revisores, 2 aprovaram', approvals: 2, reviewers: 3, changes: 0 },
  { text: '3 revisores, 1 aprovou e 1 pediu ajuste', approvals: 1, reviewers: 3, changes: 1 },
]

// Revisores de mentira para a prévia ter as fotos (as iniciais) como o badge de verdade.
const NAMES = ['Ana Lima', 'Bruno Reis', 'Carla Dias']

function people({ approvals, reviewers, changes }) {
  return NAMES.slice(0, reviewers).map((name, index) => {
    let state = 'pending'
    if (index < approvals) state = 'approved'
    else if (index < approvals + changes) state = 'changes_requested'
    return { name, state, account_id: null, avatar_url: null }
  })
}

const examples = computed(() =>
  EXAMPLES.map((example) => {
    const review = {
      approvals: example.approvals,
      reviewers: example.reviewers,
      changes_requested: example.changes,
      required: required(example.reviewers),
      people: people(example),
    }
    let status = 'pr_aberta'
    if (example.changes) status = 'ajustes_requisitados'
    else if (example.approvals >= review.required) status = 'aprovada'
    return { ...example, review, status }
  }),
)

async function save() {
  await store.save(draft.value)
}
</script>

<template>
  <section class="approval card">
    <header class="approval__header">
      <GitPullRequest :size="18" />
      <div>
        <h2 class="approval__title">Quando o PR conta como aprovado</h2>
        <p class="approval__desc">
          O badge de PR mostra quantos revisores já aprovaram — uma barra em verde para quem
          aprovou e amarelo para ajuste pedido, com o "N/X" ao lado. A regra diz a partir de quando ele
          vira <strong>Aprovada</strong>. Pedido de ajuste continua vencendo: com ele no ar, o PR não
          conta como aprovado.
        </p>
      </div>
    </header>

    <p v-if="store.error" class="approval__error" role="alert">{{ store.error }}</p>
    <p v-else-if="draft === null" class="approval__muted">Carregando…</p>

    <template v-else>
      <fieldset class="approval__fieldset">
        <legend class="field__label">Aprovações para "Aprovada"</legend>
        <div class="segmented" role="radiogroup">
          <label
            v-for="rule in APPROVAL_RULES"
            :key="rule.percent"
            class="segmented__option"
            :class="{ 'segmented__option--on': draft === rule.percent }"
          >
            <input v-model="draft" type="radio" :value="rule.percent">
            {{ rule.label }}
          </label>
        </div>
        <span v-if="current" class="field__hint">{{ current.hint }}</span>
      </fieldset>

      <div class="approval__preview">
        <h3 class="approval__sub">Como fica o badge</h3>
        <ul class="approval__examples">
          <li v-for="example in examples" :key="example.text" :data-status="example.status">
            <PrStatusBadge :status="example.status" :review="example.review" />
            <span>{{ example.text }}</span>
          </li>
        </ul>
      </div>

      <footer class="approval__footer">
        <p v-if="store.feedback" class="approval__feedback" :data-type="store.feedback.type" role="status">
          {{ store.feedback.text }}
        </p>
        <button type="button" class="btn btn--secondary" :disabled="!dirty || store.saving" @click="reset">
          Descartar
        </button>
        <button type="button" class="btn btn--primary" :disabled="!dirty || store.saving" @click="save">
          {{ store.saving ? 'Salvando…' : 'Salvar regra' }}
        </button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.approval {
  max-width: 820px;
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.approval__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

.approval__header > svg {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--color-primary);
}

.approval__title {
  margin: 0 0 4px;
  font-size: var(--text-md);
  font-weight: 600;
}

.approval__desc,
.approval__muted {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.approval__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.approval__fieldset {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  border: 0;
}

.segmented {
  display: inline-flex;
  flex-wrap: wrap;
  width: fit-content;
  max-width: 100%;
  padding: 2px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
}

.segmented__option {
  position: relative;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.segmented__option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.segmented__option--on {
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  color: var(--color-primary);
  font-weight: 600;
}

.segmented__option:has(input:focus-visible) {
  outline: 2px solid var(--color-primary-focus-ring);
}

.approval__sub {
  margin: 0 0 var(--space-2);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.approval__examples {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.approval__examples li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.approval__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.approval__feedback {
  margin: 0 auto 0 0;
  font-size: var(--text-sm);
}

.approval__feedback[data-type='success'] {
  color: var(--color-success);
}

.approval__feedback[data-type='error'] {
  color: var(--color-error);
}
</style>
