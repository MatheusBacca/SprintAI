<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Keyboard } from 'lucide-vue-next'
import { useShortcutsStore } from '@/stores/shortcuts'
import {
  SHORTCUT_ACTIONS,
  comboFromEvent,
  comboKeys,
  conflictingAction,
  validateCombo,
} from '@/utils/shortcuts'

const shortcuts = useShortcutsStore()

const draft = ref({ ...shortcuts.bindings })
const recordingAction = ref(null)
const rowError = ref({})
const feedback = ref(null)

onMounted(async () => {
  await shortcuts.load()
  draft.value = { ...shortcuts.bindings }
})
onBeforeUnmount(() => (shortcuts.recording = false))

const dirty = computed(() => SHORTCUT_ACTIONS.some((a) => draft.value[a.id] !== shortcuts.bindings[a.id]))

function setRowError(action, message) {
  rowError.value = { ...rowError.value, [action]: message }
}

function startRecording(action) {
  recordingAction.value = action
  shortcuts.recording = true
  feedback.value = null
  setRowError(action, null)
}

function stopRecording() {
  recordingAction.value = null
  shortcuts.recording = false
}

function onRecordKeydown(event, action) {
  if (recordingAction.value !== action) return
  // Tab sai do campo normalmente; o resto é capturado.
  if (event.key === 'Tab') return
  event.preventDefault()
  event.stopPropagation()
  if (event.key === 'Escape' && !event.ctrlKey && !event.altKey && !event.shiftKey) {
    stopRecording()
    return
  }
  if (['Control', 'Alt', 'Shift', 'Meta', 'AltGraph'].includes(event.key)) return

  const combo = comboFromEvent(event)
  if (!combo) {
    setRowError(action, event.metaKey ? 'A tecla Windows é do sistema.' : 'Use uma letra, um número, F1–F12 ou Espaço como tecla.')
    return
  }
  const invalid = validateCombo(combo)
  if (invalid) {
    setRowError(action, invalid)
    return
  }
  const other = conflictingAction(draft.value, combo, action)
  if (other) {
    setRowError(action, `${combo} já é o atalho de “${other.label}”.`)
    return
  }
  draft.value = { ...draft.value, [action]: combo }
  setRowError(action, null)
  stopRecording()
}

function disable(action) {
  draft.value = { ...draft.value, [action]: null }
  setRowError(action, null)
  feedback.value = null
}

function restoreDefault(action) {
  const combo = shortcuts.defaults[action]
  const other = conflictingAction(draft.value, combo, action)
  if (other) {
    setRowError(action, `${combo} já é o atalho de “${other.label}”. Mude aquele primeiro.`)
    return
  }
  draft.value = { ...draft.value, [action]: combo }
  setRowError(action, null)
  feedback.value = null
}

function discard() {
  draft.value = { ...shortcuts.bindings }
  rowError.value = {}
  feedback.value = null
}

async function save() {
  feedback.value = null
  const ok = await shortcuts.save(draft.value)
  if (ok) {
    draft.value = { ...shortcuts.bindings }
    feedback.value = { type: 'success', text: 'Atalhos salvos. Já valem em todas as telas.' }
  } else {
    feedback.value = { type: 'error', text: shortcuts.error }
  }
}
</script>

<template>
  <section class="shortcuts card">
    <header class="shortcuts__header">
      <Keyboard :size="18" />
      <div>
        <h2 class="shortcuts__title">Atalhos de teclado</h2>
        <p class="shortcuts__desc">
          Valem em qualquer tela do SprintAI, inclusive com o foco num campo de texto. Selecione um trecho
          (descrição da tarefa, comentário, o próprio lembrete) antes de apertar para usá-lo como busca.
        </p>
      </div>
    </header>

    <ul class="shortcuts__list">
      <li v-for="action in SHORTCUT_ACTIONS" :key="action.id" class="shortcuts__row" :data-action="action.id">
        <div class="shortcuts__info">
          <p class="shortcuts__label">{{ action.label }}</p>
          <p class="shortcuts__hint">{{ action.description }}</p>
          <p v-if="rowError[action.id]" class="shortcuts__error" role="alert">{{ rowError[action.id] }}</p>
        </div>

        <button
          type="button"
          class="shortcuts__recorder"
          :class="{ 'shortcuts__recorder--on': recordingAction === action.id }"
          :aria-label="`Gravar atalho para ${action.label}`"
          @click="recordingAction === action.id ? stopRecording() : startRecording(action.id)"
          @keydown="onRecordKeydown($event, action.id)"
          @blur="recordingAction === action.id && stopRecording()"
        >
          <span v-if="recordingAction === action.id" class="shortcuts__listening">Pressione a combinação… <small>Esc cancela</small></span>
          <span v-else-if="draft[action.id]" class="shortcuts__keys">
            <kbd v-for="key in comboKeys(draft[action.id])" :key="key">{{ key }}</kbd>
          </span>
          <span v-else class="shortcuts__off">Desativado</span>
        </button>

        <div class="shortcuts__row-actions">
          <button v-if="draft[action.id]" type="button" class="btn btn--secondary" @click="disable(action.id)">Desativar</button>
          <button
            v-if="draft[action.id] !== shortcuts.defaults[action.id]"
            type="button"
            class="btn btn--secondary"
            :title="`Padrão: ${shortcuts.defaults[action.id]}`"
            @click="restoreDefault(action.id)"
          >
            Padrão
          </button>
        </div>
      </li>
    </ul>

    <details class="shortcuts__rules">
      <summary>Quais combinações são aceitas?</summary>
      <ul>
        <li>Letra, número ou Espaço com <kbd>Ctrl</kbd>+<kbd>Shift</kbd>, <kbd>Alt</kbd> ou <kbd>Alt</kbd>+<kbd>Shift</kbd>; teclas F2, F4, F8 e F9 sozinhas ou com modificador.</li>
        <li><kbd>Ctrl</kbd> + tecla sozinho fica com copiar, colar, buscar e os atalhos do navegador — exceto <kbd>Ctrl</kbd>+<kbd>K</kbd>, a busca de sempre dos apps web.</li>
        <li><kbd>Ctrl</kbd>+<kbd>Alt</kbd> é o AltGr e digita caracteres (ñ, €) em teclados PT/Intl.</li>
        <li>Reservados pelo navegador/Windows, a página nunca recebe: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>N</kbd> (janela anônima), <kbd>T</kbd>, <kbd>W</kbd>, <kbd>Q</kbd>, <kbd>R</kbd>, DevTools (<kbd>I</kbd>, <kbd>J</kbd>, <kbd>C</kbd>), <kbd>Alt</kbd>+<kbd>F4</kbd>, <kbd>F5</kbd>, <kbd>F11</kbd>, <kbd>F12</kbd>…</li>
      </ul>
    </details>

    <footer class="shortcuts__footer">
      <p v-if="feedback" class="shortcuts__feedback" :data-type="feedback.type" role="status">{{ feedback.text }}</p>
      <button type="button" class="btn btn--secondary" :disabled="!dirty || shortcuts.saving" @click="discard">Descartar</button>
      <button type="button" class="btn btn--primary" :disabled="!dirty || shortcuts.saving" @click="save">
        {{ shortcuts.saving ? 'Salvando…' : 'Salvar atalhos' }}
      </button>
    </footer>
  </section>
</template>

<style scoped>
.shortcuts {
  max-width: 820px;
  padding: var(--space-5);
}

.shortcuts__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  margin-bottom: var(--space-4);
}

.shortcuts__header > svg {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--color-primary);
}

.shortcuts__title {
  margin: 0 0 4px;
  font-size: var(--text-md);
  font-weight: 600;
}

.shortcuts__desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.shortcuts__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--color-border);
}

.shortcuts__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px auto;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border);
}

.shortcuts__label {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
}

.shortcuts__hint {
  margin: 2px 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.shortcuts__error {
  margin: 6px 0 0;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-error);
}

.shortcuts__recorder {
  min-height: 38px;
  padding: 6px 10px;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  text-align: center;
}

.shortcuts__recorder:hover {
  border-color: var(--color-primary);
}

.shortcuts__recorder--on {
  border-style: solid;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.shortcuts__listening {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.shortcuts__listening small {
  display: block;
  font-weight: 400;
  color: var(--color-text-muted);
}

.shortcuts__off {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.shortcuts__row-actions {
  display: flex;
  gap: 6px;
  min-width: 170px;
  justify-content: flex-end;
}

.shortcuts__row-actions .btn {
  padding: 5px 10px;
  font-size: var(--text-xs);
}

kbd {
  display: inline-block;
  min-width: 22px;
  margin: 0 2px;
  padding: 1px 6px;
  border: 1px solid var(--color-border-strong);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--color-surface-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  color: var(--color-text);
}

.shortcuts__rules {
  margin-top: var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.shortcuts__rules summary {
  cursor: pointer;
  font-weight: 600;
}

.shortcuts__rules ul {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-5);
  line-height: 22px;
}

.shortcuts__rules kbd {
  min-width: 0;
  font-size: 10px;
  line-height: 14px;
}

.shortcuts__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.shortcuts__feedback {
  margin: 0 auto 0 0;
  font-size: var(--text-sm);
}

.shortcuts__feedback[data-type='success'] {
  color: var(--color-success);
}

.shortcuts__feedback[data-type='error'] {
  color: var(--color-error);
}

@media (max-width: 720px) {
  .shortcuts__row {
    grid-template-columns: 1fr;
  }

  .shortcuts__row-actions {
    justify-content: flex-start;
  }
}
</style>
