<script setup>
import { ref } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: Array, required: true },
  placeholder: { type: String, default: '' },
  // (texto) => valor normalizado ou null se inválido
  normalize: { type: Function, default: (v) => v.trim() || null },
  invalidMessage: { type: String, default: 'Valor inválido' },
  prefix: { type: String, default: '' },
  inputId: { type: String, default: undefined },
  // Tags aceitam espaço (viram hífen); chaves de tarefa podem vir coladas separadas por espaço.
  separator: { type: RegExp, default: () => /[,;]+/ },
})
const emit = defineEmits(['update:modelValue'])

const text = ref('')
const error = ref(null)

function commit() {
  const parts = text.value.split(props.separator).map((p) => p.trim()).filter(Boolean)
  if (!parts.length) return
  const next = [...props.modelValue]
  for (const part of parts) {
    const value = props.normalize(part)
    if (value === null) {
      error.value = `${props.invalidMessage}: ${part}`
      return
    }
    if (!next.includes(value)) next.push(value)
  }
  error.value = null
  text.value = ''
  emit('update:modelValue', next)
}

function onKeydown(event) {
  if (['Enter', ',', 'Tab'].includes(event.key) && text.value.trim()) {
    event.preventDefault()
    commit()
  } else if (event.key === 'Backspace' && !text.value && props.modelValue.length) {
    emit('update:modelValue', props.modelValue.slice(0, -1))
  }
}

function remove(value) {
  emit('update:modelValue', props.modelValue.filter((v) => v !== value))
}
</script>

<template>
  <div class="chips">
    <div class="chips-input" :class="{ 'chips-input--error': error }">
      <span v-for="value in modelValue" :key="value" class="chips-input__chip">
        {{ prefix }}{{ value }}
        <button type="button" :aria-label="`Remover ${value}`" @click="remove(value)"><X :size="12" /></button>
      </span>
      <input
        :id="inputId"
        v-model="text"
        class="chips-input__field"
        :placeholder="modelValue.length ? '' : placeholder"
        @keydown="onKeydown"
        @blur="commit"
      >
    </div>
    <p v-if="error" class="chips-input__error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.chips-input {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 38px;
  padding: 5px 8px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.chips-input:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.chips-input--error {
  border-color: var(--color-error);
}

.chips-input__chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px 2px 8px;
  border-radius: 999px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.chips-input__chip button {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: none;
  color: inherit;
}

.chips-input__chip button:hover {
  background: var(--color-chip);
}

.chips-input__field {
  flex: 1;
  min-width: 120px;
  border: 0;
  outline: 0;
  font: inherit;
  font-size: var(--text-sm);
  background: transparent;
}

.chips-input__error {
  margin: 4px 0 0;
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
