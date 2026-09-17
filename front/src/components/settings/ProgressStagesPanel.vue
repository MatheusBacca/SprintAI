<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, GaugeCircle } from 'lucide-vue-next'
import { useProgressStore } from '@/stores/progress'

/**
 * Configurações › Progresso (B9).
 *
 * A categoria do Jira não serve para este workflow: `DISPONIVEL PARA REVIEW` e
 * `DISPONIVEL PARA TESTES` chegam como `new` e contariam como "nem começou". Aqui o dev
 * ordena as etapas, dá peso a cada uma e diz em qual etapa cai cada status do espelho.
 */
const store = useProgressStore()

const stages = ref([])
const statuses = ref({})

function reset() {
  stages.value = store.stages.map((stage) => ({ ...stage }))
  statuses.value = Object.fromEntries(
    store.statuses.map((status) => [status.status, status.stage_id ?? '']),
  )
}

onMounted(async () => {
  await store.load()
  reset()
})
watch(() => store.stages, reset)

function move(index, delta) {
  const target = index + delta
  if (target < 0 || target >= stages.value.length) return
  const list = [...stages.value]
  ;[list[index], list[target]] = [list[target], list[index]]
  stages.value = list.map((stage, order) => ({ ...stage, order }))
}

const known = computed(() => new Set(stages.value.map((s) => s.id)))
const dirty = computed(
  () =>
    JSON.stringify(stages.value) !== JSON.stringify(store.stages) ||
    JSON.stringify(statuses.value) !==
      JSON.stringify(Object.fromEntries(store.statuses.map((s) => [s.status, s.stage_id ?? '']))),
)

async function save() {
  const payload = {
    stages: stages.value.map((stage, order) => ({
      id: stage.id,
      label: stage.label,
      order,
      weight: Math.min(1, Math.max(0, Number(stage.weight))),
      color: stage.color,
    })),
    statuses: Object.fromEntries(
      Object.entries(statuses.value).filter(([, stageId]) => stageId && known.value.has(stageId)),
    ),
  }
  await store.save(payload)
}
</script>

<template>
  <section class="panel">
    <header class="panel__header">
      <GaugeCircle :size="18" class="panel__icon" />
      <div>
        <h2 class="panel__title">Progresso</h2>
        <p class="panel__hint">
          O progresso da sprint é a média dos pesos, ponderada por Story Points (tarefa sem SP conta 1).
          A categoria do Jira só é usada para status que não estiverem na tabela de baixo.
        </p>
      </div>
    </header>

    <p v-if="store.error" class="panel__error" role="alert">{{ store.error }}</p>
    <p v-else-if="store.loading && !stages.length" class="panel__muted">Carregando…</p>

    <template v-else>
      <h3 class="panel__sub">Etapas</h3>
      <ul class="stages">
        <li v-for="(stage, index) in stages" :key="stage.id" class="stage" :data-stage="stage.id">
          <span class="stage__order">
            <button type="button" :disabled="index === 0" aria-label="Subir" @click="move(index, -1)">
              <ArrowUp :size="12" />
            </button>
            <button
              type="button"
              :disabled="index === stages.length - 1"
              aria-label="Descer"
              @click="move(index, 1)"
            >
              <ArrowDown :size="12" />
            </button>
          </span>
          <input v-model="stage.label" class="field__input stage__label" :aria-label="`Nome da etapa ${stage.id}`">
          <label class="stage__weight">
            peso
            <input
              v-model.number="stage.weight"
              class="field__input"
              type="number"
              min="0"
              max="1"
              step="0.05"
              :aria-label="`Peso da etapa ${stage.label}`"
            >
          </label>
          <input v-model="stage.color" type="color" class="stage__color" :aria-label="`Cor da etapa ${stage.label}`">
        </li>
      </ul>

      <h3 class="panel__sub">Status do espelho</h3>
      <table class="statuses">
        <thead>
          <tr>
            <th>Status</th>
            <th>Categoria no Jira</th>
            <th>Tarefas</th>
            <th>Etapa</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="status in store.statuses" :key="status.status">
            <td class="statuses__name">{{ status.status }}</td>
            <td><span class="statuses__category" :data-category="status.status_category">{{ status.status_category }}</span></td>
            <td>{{ status.issue_count }}</td>
            <td>
              <select v-model="statuses[status.status]" class="field__input" :aria-label="`Etapa de ${status.status}`">
                <option value="">— pela categoria —</option>
                <option v-for="stage in stages" :key="stage.id" :value="stage.id">{{ stage.label }}</option>
              </select>
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="panel__footer">
        <button type="button" class="btn btn--secondary" :disabled="!dirty || store.saving" @click="reset">
          Descartar
        </button>
        <button type="button" class="btn btn--primary" :disabled="!dirty || store.saving" @click="save">
          {{ store.saving ? 'Salvando…' : 'Salvar etapas' }}
        </button>
        <p v-if="store.feedback" class="panel__feedback" :data-type="store.feedback.type">
          {{ store.feedback.text }}
        </p>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.panel__header {
  display: flex;
  gap: var(--space-3);
}

.panel__icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-primary);
}

.panel__title {
  margin: 0 0 2px;
  font-size: var(--text-md);
  font-weight: 600;
}

.panel__hint,
.panel__muted {
  margin: 0;
  font-size: var(--text-xs);
  line-height: 17px;
  color: var(--color-text-muted);
}

.panel__error {
  margin: 0;
  color: var(--color-error);
}

.panel__sub {
  margin: var(--space-2) 0 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.stages {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.stage {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.stage__order {
  display: flex;
  flex-direction: column;
}

.stage__order button {
  display: flex;
  padding: 1px 3px;
  border: 0;
  background: none;
  color: var(--color-text-muted);
}

.stage__order button:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.stage__label {
  flex: 1;
  min-width: 120px;
}

.stage__weight {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.stage__weight input {
  width: 78px;
}

.stage__color {
  width: 36px;
  height: 32px;
  padding: 2px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.statuses {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.statuses th {
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border-strong);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
  text-align: left;
}

.statuses td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--color-border);
}

.statuses__name {
  font-weight: 500;
}

.statuses__category {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.statuses__category[data-category='done'] {
  background: var(--color-success-surface);
  color: var(--color-success);
}

.statuses__category[data-category='indeterminate'] {
  background: var(--color-info-surface);
  color: var(--color-info);
}

.panel__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-2);
}

.panel__feedback {
  margin: 0;
  font-size: var(--text-sm);
}

.panel__feedback[data-type='success'] {
  color: var(--color-success);
}

.panel__feedback[data-type='error'] {
  color: var(--color-error);
}
</style>
