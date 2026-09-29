<script setup>
import { computed } from 'vue'
import { X } from 'lucide-vue-next'

/**
 * Chips das etapas de Configurações › Progresso, um por etapa, na ordem e na cor de lá.
 * Liga mais de um de uma vez: o canvas fica com quem cai em qualquer um dos ligados.
 */
const props = defineProps({
  stages: { type: Array, required: true },
  /** Tarefas da sprint em cada etapa, por id. */
  counts: { type: Object, default: () => ({}) },
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const ordered = computed(() => [...props.stages].sort((a, b) => a.order - b.order))

function toggle(id) {
  const on = props.modelValue.includes(id)
  emit('update:modelValue', on ? props.modelValue.filter((s) => s !== id) : [...props.modelValue, id])
}
</script>

<template>
  <div class="stages" role="group" aria-label="Filtrar por etapa">
    <button
      v-for="stage in ordered"
      :key="stage.id"
      type="button"
      class="stages__chip"
      :style="{ '--tone': stage.color }"
      :aria-pressed="modelValue.includes(stage.id)"
      :title="modelValue.includes(stage.id) ? `Parar de filtrar por ${stage.label}` : `Mostrar só as tarefas em ${stage.label}`"
      @click="toggle(stage.id)"
    >
      <span class="stages__dot" aria-hidden="true" />
      <!-- Na mesma linha: o espaço entre os dois fica no texto (leitor de tela diria
           "Análise0"), e no flex ele não desenha nada. -->
      <span class="stages__label">{{ stage.label }}</span> <span class="stages__count">{{ counts[stage.id] ?? 0 }}</span>
    </button>
    <button
      v-if="modelValue.length"
      type="button"
      class="stages__clear"
      aria-label="Limpar filtro de etapas"
      title="Limpar filtro de etapas"
      @click="emit('update:modelValue', [])"
    >
      <X :size="12" />
    </button>
  </div>
</template>

<style scoped>
/* Uma linha só, abaixo do seletor. As cinco etapas e o X cabem nos 480px do painel com
   ~18px de folga — medido: com 1px a menos cada nome já ganhava reticências. Em painel
   mais estreito quem cede é o nome da etapa, e o nome inteiro fica no title. */
.stages {
  display: flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}

.stages__chip {
  flex: 0 1 auto;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: none;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.stages__chip:hover {
  background: var(--color-surface-hover);
}

.stages__chip[aria-pressed='true'] {
  border-color: color-mix(in srgb, var(--tone) 65%, transparent);
  background: color-mix(in srgb, var(--tone) 16%, var(--color-surface));
  color: var(--color-text);
}

.stages__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stages__dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--tone);
}

.stages__count {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
}

.stages__clear {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
}
</style>
