<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'
import ChipsInput from '@/components/notes/ChipsInput.vue'
import { CONTEXT_KINDS, CONTEXT_KIND_KEYS } from '@/constants/contextKinds'
import { useContextsStore } from '@/stores/contexts'

const store = useContextsStore()
const draft = computed(() => store.editor.draft)
const titleInput = ref(null)
const issueInput = ref(null)

const KEY = /^[A-Z][A-Z0-9]{1,9}-\d{1,7}$/
const normalizeTag = (value) => value.replace(/^#/, '').trim().toLowerCase().replace(/\s+/g, '-').slice(0, 40) || null
const normalizeKey = (value) => {
  const key = value.trim().toUpperCase()
  return KEY.test(key) ? key : null
}

const kind = computed(() => CONTEXT_KINDS[draft.value.kind])
// Ponto já resolvido não muda de tipo (o back recusa): reabra antes.
const kindLocked = computed(() => draft.value.status === 'resolved')
const issueInvalid = computed(() => draft.value.issue_key.trim() !== '' && !KEY.test(draft.value.issue_key.trim().toUpperCase()))
const continuesInvalid = computed(() => draft.value.continues_key.trim() !== '' && !KEY.test(draft.value.continues_key.trim().toUpperCase()))
const canSave = computed(
  () => !store.editor.saving && KEY.test(draft.value.issue_key.trim().toUpperCase()) && !continuesInvalid.value && (draft.value.title.trim() || draft.value.body.trim()),
)

watch(
  () => store.editor.open,
  async (open) => {
    if (!open) return
    await nextTick()
    if (draft.value.issue_key) titleInput.value?.focus()
    else issueInput.value?.focus()
  },
)

function uppercase(field) {
  draft.value[field] = draft.value[field].toUpperCase()
}

async function save() {
  if (canSave.value) await store.saveEditor()
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    store.closeEditor()
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    save()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="store.editor.open" class="ctx-backdrop" @mousedown.self="store.closeEditor()">
      <form
        class="ctx-editor"
        role="dialog"
        aria-modal="true"
        :aria-label="draft.id ? 'Editar contexto' : 'Novo contexto'"
        :style="{ '--kind-color': kind.color, '--kind-bg': kind.bg }"
        @submit.prevent="save"
        @keydown="onKeydown"
      >
        <header class="ctx-editor__header">
          <h2>{{ draft.id ? 'Editar contexto' : 'Novo contexto' }}</h2>
          <button type="button" class="ctx-editor__icon" title="Fechar (Esc)" @click="store.closeEditor()"><X :size="16" /></button>
        </header>

        <div class="ctx-editor__kinds" role="radiogroup" aria-label="Tipo">
          <button
            v-for="key in CONTEXT_KIND_KEYS"
            :key="key"
            type="button"
            role="radio"
            class="ctx-editor__kind"
            :aria-checked="draft.kind === key"
            :disabled="kindLocked && draft.kind !== key"
            :title="kindLocked && draft.kind !== key ? 'Reabra o ponto para mudar o tipo' : CONTEXT_KINDS[key].hint"
            :style="{ '--k-color': CONTEXT_KINDS[key].color, '--k-bg': CONTEXT_KINDS[key].bg }"
            @click="draft.kind = key"
          >
            <component :is="CONTEXT_KINDS[key].icon" :size="14" />
            {{ CONTEXT_KINDS[key].label }}
          </button>
        </div>
        <p class="ctx-editor__hint">{{ kind.hint }}</p>

        <div class="ctx-editor__row">
          <div class="field ctx-editor__issue">
            <label class="field__label" for="ctx-issue">Tarefa</label>
            <input
              id="ctx-issue"
              ref="issueInput"
              v-model="draft.issue_key"
              class="field__input"
              :class="{ 'field__input--error': issueInvalid }"
              placeholder="WAI-1234"
              maxlength="20"
              @blur="uppercase('issue_key')"
            >
          </div>
          <div class="field ctx-editor__title-field">
            <label class="field__label" for="ctx-title">Título</label>
            <input id="ctx-title" ref="titleInput" v-model="draft.title" class="field__input" maxlength="200" placeholder="Resumo em uma linha">
          </div>
        </div>

        <div class="field">
          <label class="field__label" for="ctx-body">Detalhes</label>
          <textarea
            id="ctx-body"
            v-model="draft.body"
            class="field__input ctx-editor__body"
            rows="8"
            maxlength="20000"
            placeholder="O que aconteceu, onde (arquivo, endpoint, query), como reproduzir, o que ficou decidido…"
          />
        </div>

        <div class="ctx-editor__grid">
          <div class="field">
            <label class="field__label" for="ctx-related">Tarefas relacionadas</label>
            <ChipsInput v-model="draft.related_keys" input-id="ctx-related" placeholder="WAI-1200" :normalize="normalizeKey" :separator="/[,;\s]+/" invalid-message="Chave inválida" />
          </div>
          <div class="field">
            <label class="field__label" for="ctx-continues">Continua a tarefa</label>
            <input
              id="ctx-continues"
              v-model="draft.continues_key"
              class="field__input"
              :class="{ 'field__input--error': continuesInvalid }"
              placeholder="Opcional — tarefa anterior"
              maxlength="20"
              @blur="uppercase('continues_key')"
            >
          </div>
          <div class="field">
            <label class="field__label" for="ctx-tags">Tags</label>
            <ChipsInput v-model="draft.tags" input-id="ctx-tags" prefix="#" placeholder="retry, fila…" :normalize="normalizeTag" invalid-message="Tag inválida" />
          </div>
        </div>

        <footer class="ctx-editor__footer">
          <p v-if="store.editor.error" class="ctx-editor__error" role="alert">{{ store.editor.error }}</p>
          <span class="ctx-editor__shortcut">Ctrl+Enter salva</span>
          <button type="button" class="btn btn--secondary" @click="store.closeEditor()">Cancelar</button>
          <button type="submit" class="btn btn--primary" :disabled="!canSave">
            {{ store.editor.saving ? 'Salvando…' : 'Salvar' }}
          </button>
        </footer>
      </form>
    </div>
  </Teleport>
</template>

<style scoped>
.ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: start center;
  overflow-y: auto;
  padding: 8vh var(--space-4) var(--space-4);
  background: var(--color-overlay);
}

.ctx-editor {
  width: min(720px, 100%);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5) var(--space-5);
  border: 1px solid var(--color-border);
  border-top: 5px solid var(--kind-color);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.ctx-editor__header {
  display: flex;
  align-items: center;
}

.ctx-editor__header h2 {
  flex: 1;
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.ctx-editor__icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.ctx-editor__icon:hover {
  background: var(--color-surface-muted);
}

.ctx-editor__kinds {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ctx-editor__kind {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.ctx-editor__kind[aria-checked='true'] {
  border-color: var(--k-color);
  background: var(--k-bg);
  color: var(--k-color);
  font-weight: 600;
}

.ctx-editor__kind:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ctx-editor__hint {
  margin: -4px 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.ctx-editor__row {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: var(--space-3);
}

.ctx-editor__body {
  resize: vertical;
  line-height: 21px;
}

.ctx-editor__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: var(--space-3);
}

.field__input--error {
  border-color: var(--color-error);
}

.ctx-editor__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.ctx-editor__shortcut {
  margin-right: auto;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.ctx-editor__error {
  flex-basis: 100%;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

@media (max-width: 560px) {
  .ctx-editor__row {
    grid-template-columns: 1fr;
  }
}
</style>
