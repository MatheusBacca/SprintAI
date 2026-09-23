<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ChevronRight, ExternalLink, LoaderCircle } from 'lucide-vue-next'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Linha de fluxo do Jira para mover a tarefa: clique escolhe, duplo clique confirma e
 * move. O duplo clique é a confirmação que a regra de escrita pede — um clique perdido
 * não muda nada no Jira.
 *
 * Os passos vêm na ordem das etapas de Configurações › Progresso, com todos os status do
 * workflow: os que não têm transição a partir do atual aparecem apagados, para a linha
 * mostrar onde a tarefa está e o que o workflow não deixa pular.
 *
 * A linha principal é a das etapas; o resto vai para "Outros status", recolhido. O
 * workflow de Tarefa da WAI é global e compartilhado com outros times — são 17 status,
 * de "Cruzeiro" a "IMPLANTAÇÃO" — e, abertos todos, o fluxo do board sumia no meio.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
})

const store = useJiraActionsStore()
const selected = ref(null)
const list = ref(null)
const showOthers = ref(false)

const flow = computed(() =>
  store.flow.key === props.issueKey ? store.flow : { data: null, loading: true, error: null },
)
const steps = computed(() => flow.value.data?.steps ?? [])
const current = computed(() => steps.value.find((s) => s.current)?.status ?? flow.value.data?.status)
const jiraUrl = computed(() => safeUrl(flow.value.data?.url))
const selectedStep = computed(() => steps.value.find((s) => s.transition_id && s.transition_id === selected.value))

/** O atual fica sempre na linha principal, mesmo sem etapa: é dele que tudo parte. */
const groups = computed(() => {
  const main = steps.value.filter((s) => s.stage || s.current)
  const others = steps.value.filter((s) => !s.stage && !s.current)
  // Sem etapas mapeadas não há linha para destacar: mostra tudo junto.
  if (main.length < 2) return { main: steps.value, others: [] }
  return { main, others }
})

function available(step) {
  return Boolean(step.transition_id) && !step.requires_fields
}

function choose(step, event) {
  if (!available(step) || store.saving) return
  // Enter/Espaço chegam como clique com `detail` 0: o segundo Enter no passo já escolhido
  // confirma — é o duplo clique de quem está no teclado.
  if (event?.detail === 0 && selected.value === step.transition_id) {
    confirm(step)
    return
  }
  selected.value = step.transition_id
}

function confirm(step) {
  if (!available(step) || store.saving) return
  selected.value = step.transition_id
  store.transition(props.issueKey, step.transition_id)
}

function note(step) {
  if (step.current) return 'atual'
  if (step.requires_fields) return 'pede campos no Jira'
  return step.stage?.label ?? ''
}

function title(step) {
  if (step.current) return `${props.issueKey} está em ${step.status}`
  if (step.requires_fields) return `A transição “${step.transition_name}” pede campos no Jira — faça por lá`
  if (!step.transition_id) return `O workflow não leva de ${current.value} para ${step.status}`
  const via = step.transition_name && step.transition_name !== step.status ? ` (transição “${step.transition_name}”)` : ''
  return `Duplo clique para mover para ${step.status}${via}`
}

const hint = computed(() => {
  if (store.saving && selectedStep.value) return `Movendo para ${selectedStep.value.status} no Jira…`
  if (selectedStep.value) return `Duplo clique em ${selectedStep.value.status} (ou Enter de novo) move no Jira`
  return 'Clique escolhe · duplo clique move no Jira'
})

// Com a lista na tela, o foco pousa no primeiro passo possível: dá para escolher pelo
// teclado sem caçar o painel com o Tab.
watch(
  () => flow.value.data,
  async (data) => {
    selected.value = null
    showOthers.value = false
    if (!data) return
    await nextTick()
    list.value?.querySelector('button:not(:disabled)')?.focus()
  },
  { immediate: true },
)
</script>

<template>
  <div class="flow">
    <header class="flow__head">
      <strong class="flow__title">Mover {{ issueKey }}</strong>
      <a v-if="jiraUrl" class="flow__jira" :href="jiraUrl" target="_blank" rel="noopener noreferrer">
        Abrir no Jira <ExternalLink :size="11" />
      </a>
    </header>

    <p v-if="flow.loading" class="flow__state"><LoaderCircle :size="14" class="spin" /> Lendo o fluxo no Jira…</p>
    <p v-else-if="flow.error" class="flow__error" role="alert">{{ flow.error }}</p>

    <template v-else>
      <p v-if="flow.data.mirror_status" class="flow__note">
        No Jira ela já está em <strong>{{ flow.data.status }}</strong> — a tela mostrava {{ flow.data.mirror_status }}.
      </p>

      <div ref="list">
        <template v-for="group in ['main', 'others']" :key="group">
          <button
            v-if="group === 'others' && groups.others.length"
            type="button"
            class="flow__toggle"
            :aria-expanded="showOthers"
            title="Status do workflow sem etapa em Configurações › Progresso — mapeie lá para entrarem na linha"
            @click="showOthers = !showOthers"
          >
            <ChevronRight :size="13" class="flow__toggle-icon" aria-hidden="true" />
            Outros status ({{ groups.others.length }})
          </button>
          <ol
            v-if="group === 'main' || showOthers"
            class="flow__steps"
            :class="{ 'flow__steps--others': group === 'others' }"
            :aria-label="group === 'main' ? `Fluxo de ${issueKey}` : 'Outros status do workflow'"
          >
            <li
              v-for="step in groups[group]"
              :key="step.status"
              class="flow__step"
              :class="{
                'flow__step--current': step.current,
                'flow__step--blocked': !step.current && !available(step),
                'flow__step--selected': selected && selected === step.transition_id,
              }"
              :style="{ '--tone': step.stage?.color ?? 'var(--color-border-strong)' }"
              :data-status="step.status"
            >
              <button
                v-if="available(step)"
                type="button"
                class="flow__option"
                :disabled="store.saving"
                :aria-pressed="selected === step.transition_id"
                :title="title(step)"
                @click="choose(step, $event)"
                @dblclick="confirm(step)"
              >
                <span class="flow__dot" aria-hidden="true" />
                <span class="flow__name">{{ step.status }}</span>
                <LoaderCircle v-if="store.saving && selected === step.transition_id" :size="13" class="spin flow__note-icon" />
                <span v-else class="flow__meta">{{ note(step) }}</span>
              </button>
              <div v-else class="flow__option" :title="title(step)" :aria-current="step.current ? 'step' : undefined" :aria-disabled="!step.current || null">
                <span class="flow__dot" aria-hidden="true" />
                <span class="flow__name">{{ step.status }}</span>
                <span class="flow__meta">{{ note(step) }}</span>
              </div>
            </li>
          </ol>
        </template>
      </div>

      <p class="flow__hint" aria-live="polite">{{ hint }}</p>
      <p v-if="store.error" class="flow__error" role="alert">{{ store.error }}</p>
    </template>
  </div>
</template>

<style scoped>
.flow {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 280px;
}

.flow__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}

.flow__title {
  font-size: var(--text-sm);
}

.flow__jira {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--text-xs);
  color: var(--color-primary);
}

.flow__jira:hover {
  text-decoration: underline;
}

.flow__state,
.flow__hint,
.flow__note {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.flow__note {
  display: block;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
}

.flow__error {
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  font-size: var(--text-xs);
  color: var(--color-error);
}

/* Trilho vertical ligando os passos, atrás das bolinhas. */
.flow__steps {
  position: relative;
  margin: 0;
  padding: 0;
  list-style: none;
}

.flow__steps::before {
  content: '';
  position: absolute;
  top: 14px;
  bottom: 14px;
  left: 13px;
  width: 2px;
  border-radius: 1px;
  background: var(--color-border-strong);
}

.flow__option {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: none;
  text-align: left;
  color: var(--color-text);
}

button.flow__option:not(:disabled):hover {
  background: var(--color-surface-hover);
}

.flow__step--selected .flow__option {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.flow__dot {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  border: 2px solid var(--tone);
  border-radius: 50%;
  background: var(--color-surface);
}

.flow__step--current .flow__dot {
  background: var(--tone);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 30%, transparent);
}

.flow__step--selected .flow__dot {
  background: var(--tone);
}

.flow__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
}

.flow__step--current .flow__name {
  font-weight: 600;
}

.flow__meta {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.flow__step--current .flow__meta {
  font-weight: 600;
  color: var(--color-text-secondary);
}

.flow__note-icon {
  flex-shrink: 0;
  color: var(--color-primary);
}

.flow__toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  margin-top: 2px;
  padding: 4px 6px;
  border: 0;
  border-top: 1px solid var(--color-border);
  border-radius: 0;
  background: none;
  font-size: var(--text-xs);
  font-weight: 600;
  text-align: left;
  color: var(--color-text-secondary);
}

.flow__toggle:hover {
  color: var(--color-primary);
}

.flow__toggle-icon {
  flex-shrink: 0;
  transition: transform var(--duration-fast);
}

.flow__toggle[aria-expanded='true'] .flow__toggle-icon {
  transform: rotate(90deg);
}

/* Fora da linha das etapas: sem trilho ligando, cada um é um status solto. */
.flow__steps--others::before {
  display: none;
}

/* Sem transição daqui: fica na linha, mas não chama clique. */
.flow__step--blocked .flow__option {
  cursor: not-allowed;
  opacity: 0.5;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
