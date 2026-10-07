<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Plus, X } from 'lucide-vue-next'
import ReviewerAvatar from './ReviewerAvatar.vue'
import { usePrReviewersStore } from '@/stores/prReviewers'
import { normalize } from '@/utils/highlight'

/**
 * Reviewers de um PR, com o pôr e o tirar pelo SprintAI — só no PR aberto. As duas escritas
 * pedem confirmação: escolher alguém mostra "Adicionar Fulano?", e o × vira "Tirar?" no
 * primeiro clique. Tirar quem já aprovou leva a aprovação junto, e o aviso diz isso.
 *
 * Depois da troca, a lista que o Bitbucket devolveu fica na tela até o espelho (que o sync,
 * chamado pelo back, atualiza) chegar com ela.
 *
 * Cada revisor é uma pílula com a foto e o nome, pintada inteira com o estado: aprovou,
 * pediu ajustes ou ainda não revisou.
 */
const props = defineProps({
  pr: { type: Object, required: true },
})

const store = usePrReviewersStore()
const editable = computed(() => props.pr.state === 'OPEN')
const saving = computed(() => Boolean(store.saving[`${props.pr.repo_slug}#${props.pr.id}`]))

/** A lista que o Bitbucket devolveu depois da troca, até o espelho chegar com ela. */
const updated = ref(null)
watch(
  () => props.pr.reviewers,
  () => (updated.value = null),
)

const reviewers = computed(() =>
  updated.value
    ? updated.value.map((r) => ({ ...r, role: 'REVIEWER', account_id: r.account_id ?? r.uuid }))
    : props.pr.reviewers,
)

const idsOf = (person) => [person.account_id, person.uuid].filter(Boolean)
const present = computed(() => new Set(reviewers.value.flatMap(idsOf)))

const error = ref(null)

// --- Tirar ---------------------------------------------------------------------------------

/** O reviewer esperando o segundo clique no ×. */
const removing = ref(null)

function removable(reviewer) {
  return editable.value && reviewer.role === 'REVIEWER' && Boolean(reviewer.account_id)
}

function removeTitle(reviewer) {
  if (removing.value !== reviewer.account_id) return `Tirar ${reviewer.name ?? 'o revisor'} do PR`
  return reviewer.approved ? 'Clique de novo para tirar — a aprovação dele sai junto' : 'Clique de novo para tirar'
}

async function onRemove(reviewer) {
  if (removing.value !== reviewer.account_id) {
    removing.value = reviewer.account_id
    return
  }
  removing.value = null
  await apply({ remove: [reviewer.account_id] })
}

// --- Pôr -----------------------------------------------------------------------------------

const picking = ref(false)
const query = ref('')
const candidate = ref(null)
const searchEl = ref(null)

const candidates = computed(() => {
  const needle = normalize(query.value.trim())
  return store.members
    .filter((m) => !m.is_me && !idsOf(m).some((id) => present.value.has(id)))
    .filter((m) => !needle || normalize(`${m.name} ${m.nickname ?? ''}`).includes(needle))
    .slice(0, 8)
})

async function startPicking() {
  picking.value = true
  candidate.value = null
  error.value = null
  store.loadMembers()
  await nextTick()
  searchEl.value?.focus()
}

function cancelPicking() {
  picking.value = false
  candidate.value = null
  query.value = ''
}

async function confirmAdd() {
  const member = candidate.value
  if (!member) return
  const ok = await apply({ add: [member.account_id ?? member.uuid] })
  if (ok) cancelPicking()
}

async function apply(change) {
  error.value = null
  try {
    const result = await store.update(props.pr.repo_slug, props.pr.id, change)
    updated.value = result.reviewers
    return true
  } catch (err) {
    error.value = err.message
    return false
  }
}

function stateOf(reviewer) {
  return reviewer.approved ? 'approved' : reviewer.state || 'pending'
}

function stateTitle(reviewer) {
  if (reviewer.approved) return 'Aprovou'
  return reviewer.state === 'changes_requested' ? 'Pediu ajustes' : 'Aguardando'
}
</script>

<template>
  <div v-if="reviewers.length || editable" class="reviewers" :data-busy="saving || null">
    <ul class="reviewers__list" aria-label="Reviewers">
      <li
        v-for="(r, i) in reviewers"
        :key="r.account_id ?? i"
        class="reviewers__chip"
        :data-state="stateOf(r)"
        :data-confirm="removing === r.account_id || null"
        :title="stateTitle(r)"
      >
        <ReviewerAvatar :name="r.name" :url="r.avatar_url" :size="16" />
        <span class="reviewers__name">{{ r.name ?? 'Revisor' }}</span>
        <button
          v-if="removable(r)"
          type="button"
          class="reviewers__remove"
          :disabled="saving"
          :title="removeTitle(r)"
          :aria-label="removing === r.account_id ? `Confirmar: tirar ${r.name}` : `Tirar ${r.name}`"
          @click="onRemove(r)"
          @blur="removing === r.account_id ? (removing = null) : null"
        >
          <span v-if="removing === r.account_id">Tirar?</span>
          <X v-else :size="11" />
        </button>
      </li>
      <li v-if="editable && !picking">
        <button type="button" class="reviewers__add" :disabled="saving" title="Pôr um reviewer neste PR" @click="startPicking">
          <Plus :size="11" /> Reviewer
        </button>
      </li>
    </ul>

    <div v-if="picking" class="reviewers__picker">
      <template v-if="candidate">
        <p class="reviewers__ask">Adicionar <strong>{{ candidate.name }}</strong> como reviewer do PR #{{ pr.id }}?</p>
        <div class="reviewers__actions">
          <button type="button" class="btn btn--primary" :disabled="saving" @click="confirmAdd">Adicionar</button>
          <button type="button" class="btn btn--secondary" :disabled="saving" @click="candidate = null">Voltar</button>
        </div>
      </template>
      <template v-else>
        <input
          ref="searchEl"
          v-model="query"
          type="search"
          class="field__input reviewers__search"
          placeholder="Buscar no workspace…"
          aria-label="Buscar reviewer"
          @keydown.esc.stop="cancelPicking"
        >
        <p v-if="store.membersLoading" class="reviewers__muted">Lendo os membros do workspace…</p>
        <p v-else-if="store.membersError" class="reviewers__error" role="alert">{{ store.membersError }}</p>
        <ul v-else class="reviewers__options">
          <li v-for="member in candidates" :key="member.account_id ?? member.uuid">
            <button type="button" class="reviewers__option" @click="candidate = member">
              {{ member.name }}<span v-if="member.nickname" class="reviewers__nick">{{ member.nickname }}</span>
            </button>
          </li>
          <li v-if="!candidates.length" class="reviewers__muted">Ninguém com esse nome fora da lista.</li>
        </ul>
        <button type="button" class="reviewers__cancel" @click="cancelPicking">Cancelar</button>
      </template>
    </div>

    <p v-if="error" class="reviewers__error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.reviewers {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 2px;
}

.reviewers[data-busy] {
  opacity: 0.7;
}

.reviewers__list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* A pílula inteira na cor do estado — as mesmas cores das fotos no badge do PR. */
.reviewers__chip {
  --chip: var(--color-text-muted);

  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 4px 1px 1px;
  border: 1px solid color-mix(in srgb, var(--chip) 40%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--chip) 14%, var(--color-surface));
  font-size: 11px;
  font-weight: 500;
  color: color-mix(in srgb, var(--chip) 55%, var(--color-text));
  --avatar-fill: color-mix(in srgb, var(--chip) 26%, var(--color-surface));
  --avatar-ink: color-mix(in srgb, var(--chip) 55%, var(--color-text));
}

.reviewers__chip[data-state='approved'] {
  --chip: var(--pr-approved);
}

.reviewers__chip[data-state='changes_requested'] {
  --chip: var(--pr-changes);
}

/* Sem o ×, a pílula fecha com o mesmo respiro do lado da foto. */
.reviewers__name:last-child {
  padding-right: 4px;
}

.reviewers__chip[data-confirm] {
  border-color: var(--color-error);
}

.reviewers__remove {
  display: inline-grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  padding: 0 2px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: var(--color-text-muted);
  font-size: 10px;
  font-weight: 600;
}

.reviewers__remove:hover:not(:disabled),
.reviewers__chip[data-confirm] .reviewers__remove {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.reviewers__add {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 8px;
  border: 1px dashed var(--color-border-strong);
  border-radius: 999px;
  background: none;
  font-size: 11px;
  color: var(--color-text-muted);
}

.reviewers__add:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.reviewers__picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
}

.reviewers__search {
  padding: 4px 8px;
  font-size: var(--text-xs);
}

.reviewers__options {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.reviewers__option {
  width: 100%;
  padding: 4px 6px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font-size: var(--text-xs);
  color: var(--color-text);
  text-align: left;
}

.reviewers__option:hover {
  background: var(--color-surface-hover);
}

.reviewers__nick {
  margin-left: 6px;
  color: var(--color-text-muted);
}

.reviewers__ask,
.reviewers__muted {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.reviewers__ask {
  color: var(--color-text);
}

.reviewers__actions {
  display: flex;
  gap: 6px;
}

.reviewers__cancel {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  font-size: 11px;
  color: var(--color-text-muted);
}

.reviewers__error {
  margin: 0;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-error-surface);
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
