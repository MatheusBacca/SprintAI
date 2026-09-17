<script setup>
import { ref } from 'vue'
import { ChevronDown, ChevronUp, Search, X } from 'lucide-vue-next'

/**
 * Busca dentro do canvas da sprint. Só a caixa: quem acha as tarefas e move a
 * câmera é a `SprintView` — aqui não há acesso ao Vue Flow. Ela abre no Ctrl+F,
 * no lugar da busca do navegador, que não enxerga dentro do canvas.
 */
defineProps({
  modelValue: { type: String, default: '' },
  count: { type: Number, default: 0 },
  /** Posição do resultado em foco, base 1. Zero quando não há nenhum. */
  position: { type: Number, default: 0 },
})
const emit = defineEmits(['update:modelValue', 'next', 'prev', 'close'])

const input = ref(null)

/** Ctrl+F com a caixa já aberta: volta o foco e seleciona o termo, como no navegador. */
function focus() {
  input.value?.focus()
  input.value?.select()
}

defineExpose({ focus })

function onKeydown(event) {
  if (event.key === 'Enter') {
    event.preventDefault()
    emit(event.shiftKey ? 'prev' : 'next')
  } else if (event.key === 'Escape') {
    // Sem stopPropagation o Esc chegaria à janela e fecharia também a tarefa aberta.
    event.preventDefault()
    event.stopPropagation()
    emit('close')
  }
}
</script>

<template>
  <div class="find" :class="{ 'find--empty': modelValue && !count }">
    <Search :size="14" class="find__icon" />
    <input
      ref="input"
      :value="modelValue"
      type="search"
      class="find__input"
      placeholder="Achar no canvas: chave ou título"
      aria-label="Buscar tarefa no canvas"
      maxlength="120"
      @input="emit('update:modelValue', $event.target.value)"
      @keydown="onKeydown"
    >

    <span v-if="modelValue" class="find__count" role="status">{{ count ? `${position}/${count}` : 'nada' }}</span>
    <template v-if="modelValue">
      <button type="button" class="find__nav" title="Anterior (Shift+Enter)" aria-label="Resultado anterior" :disabled="count < 2" @click="emit('prev')">
        <ChevronUp :size="14" />
      </button>
      <button type="button" class="find__nav" title="Próximo (Enter)" aria-label="Próximo resultado" :disabled="count < 2" @click="emit('next')">
        <ChevronDown :size="14" />
      </button>
    </template>
    <button type="button" class="find__nav" title="Fechar (Esc)" aria-label="Fechar busca" @click="emit('close')">
      <X :size="14" />
    </button>
  </div>
</template>

<style scoped>
.find {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 1 320px;
  min-width: 180px;
  padding: 3px 6px 3px 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  transition: border-color var(--duration-fast);
}

.find:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.find--empty {
  border-color: var(--color-warning-border);
}

.find__icon {
  flex-shrink: 0;
  color: var(--color-text-muted);
}

.find__input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.find__input::-webkit-search-cancel-button {
  display: none;
}

.find__count {
  flex-shrink: 0;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.find__nav {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-secondary);
}

.find__nav:not(:disabled):hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.find__nav:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
