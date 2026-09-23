<script setup>
import { computed, onMounted, ref } from 'vue'
import { useJiraActionsStore } from '@/stores/jiraActions'

/**
 * Editor de Story Points. Os atalhos são a sequência de Fibonacci da régua da WeON (13
 * já é sinal de quebrar a tarefa); qualquer outro valor vai pelo campo. Clique num atalho
 * preenche, duplo clique grava — o mesmo gesto de confirmar do status.
 *
 * Campo vazio não apaga: sem querer, Enter num campo limpo tiraria os pontos da tarefa
 * no Jira. Tirar é o botão "Remover", com o nome da ação escrito.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
  points: { type: Number, default: null },
})

const SUGGESTIONS = [1, 2, 3, 5, 8, 13]
const MAX_POINTS = 999

const store = useJiraActionsStore()
const draft = ref(props.points != null ? String(props.points) : '')
const input = ref(null)

/** Número digitado (vírgula vale), `null` com o campo vazio, `NaN` para o inválido. */
function parse(text) {
  const value = text.trim().replace(',', '.')
  if (!value) return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 && number <= MAX_POINTS ? number : Number.NaN
}

const parsed = computed(() => parse(draft.value))
const invalid = computed(() => Number.isNaN(parsed.value))
const empty = computed(() => parsed.value === null)

function save(value) {
  if (value === null || Number.isNaN(value) || store.saving) return
  // Mesmo valor: nada a escrever no Jira, só fecha.
  if (value === props.points) {
    store.close()
    return
  }
  store.savePoints(props.issueKey, value)
}

function remove() {
  if (!store.saving) store.savePoints(props.issueKey, null)
}

onMounted(() => {
  input.value?.focus()
  input.value?.select()
})
</script>

<template>
  <form class="points" @submit.prevent="save(parsed)">
    <strong class="points__title">Story Points de {{ issueKey }}</strong>

    <div class="points__suggestions" role="group" aria-label="Valores da régua">
      <button
        v-for="n in SUGGESTIONS"
        :key="n"
        type="button"
        class="points__pick"
        :class="{ 'points__pick--on': parsed === n }"
        :aria-pressed="parsed === n"
        :disabled="store.saving"
        :title="`Duplo clique grava ${n} SP`"
        @click="draft = String(n)"
        @dblclick="save(n)"
      >
        {{ n }}
      </button>
    </div>

    <div class="points__row">
      <input
        ref="input"
        v-model="draft"
        class="points__input"
        type="text"
        inputmode="decimal"
        autocomplete="off"
        :aria-invalid="invalid || null"
        aria-label="Story Points"
        placeholder="—"
      >
      <button type="submit" class="btn btn--primary" :disabled="invalid || empty || store.saving">
        {{ store.saving ? 'Salvando…' : 'Salvar' }}
      </button>
    </div>

    <p v-if="invalid" class="points__error" role="alert">Use um número de 0 a {{ MAX_POINTS }}.</p>
    <p v-if="store.error" class="points__error" role="alert">{{ store.error }}</p>

    <footer class="points__foot">
      <span class="points__hint">Enter salva · duplo clique num valor grava direto</span>
      <button v-if="points != null" type="button" class="points__remove" :disabled="store.saving" @click="remove">
        Remover
      </button>
    </footer>
  </form>
</template>

<style scoped>
.points {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 248px;
}

.points__title {
  font-size: var(--text-sm);
}

.points__suggestions {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px;
}

.points__pick {
  height: 28px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.points__pick:not(:disabled):hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.points__pick--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.points__row {
  display: flex;
  gap: var(--space-2);
}

.points__input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font: inherit;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.points__input:focus {
  border-color: var(--color-primary);
  outline: none;
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.points__input[aria-invalid] {
  border-color: var(--color-error);
}

.points__error {
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  font-size: var(--text-xs);
  color: var(--color-error);
}

.points__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.points__hint {
  font-size: 11px;
  color: var(--color-text-muted);
}

.points__remove {
  flex-shrink: 0;
  padding: 2px 6px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font-size: var(--text-xs);
  color: var(--color-error);
}

.points__remove:not(:disabled):hover {
  background: var(--color-error-surface);
}
</style>
