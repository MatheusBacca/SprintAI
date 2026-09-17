<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { BellOff, Check, Pin, X } from 'lucide-vue-next'
import ChipsInput from './ChipsInput.vue'
import LinksField from './LinksField.vue'
import MentionTextarea from './MentionTextarea.vue'
import { NOTE_COLORS, NOTE_COLOR_KEYS } from '@/constants/noteColors'
import { useNotesStore } from '@/stores/notes'
import { useSyncStore } from '@/stores/sync'
import { fromLocalInput, reminderPresets, toLocalInput } from '@/utils/datetime'
import { mentionsIn, normalizeTag } from '@/utils/noteTokens'

const store = useNotesStore()
const sync = useSyncStore()
const draft = computed(() => store.editor.draft)
const titleInput = ref(null)

const tagNames = computed(() => (Array.isArray(store.tags) ? store.tags.map((t) => t.tag) : []))

/** Sugestões do texto só carregam quando o dev digita o primeiro `#` ou `@`. */
function loadSuggestions(char) {
  if (char === '#' && !tagNames.value.length) store.loadTags()
  if (char === '@' && !sync.scope) sync.loadScope().catch(() => {})
}

/**
 * O que entrou no lembrete por menção no texto (ou já estava citado quando ele abriu).
 * Só isso é limpo quando a menção some da descrição: vínculo e tag escolhidos nos
 * próprios campos não dependem do texto e ficam.
 */
const FIELDS = { tag: 'tags', repo: 'repos', issue: 'issue_keys' }
let mentioned = { tag: new Set(), repo: new Set(), issue: new Set() }

function trackMentionsOnOpen() {
  const found = mentionsIn(draft.value.body)
  mentioned = Object.fromEntries(
    Object.entries(FIELDS).map(([kind, field]) => [kind, new Set(draft.value[field].filter((v) => found[kind].has(v)))]),
  )
}

function addMention(kind, value) {
  const list = draft.value[FIELDS[kind]]
  if (value && !list.includes(value)) list.push(value)
  mentioned[kind].add(value)
}

/** Ao sair da descrição: citou e depois apagou do texto, o vínculo (ou a tag) sai junto. */
function pruneMentions() {
  const found = mentionsIn(draft.value.body)
  for (const [kind, field] of Object.entries(FIELDS)) {
    for (const value of [...mentioned[kind]]) {
      if (found[kind].has(value)) continue
      mentioned[kind].delete(value)
      draft.value[field] = draft.value[field].filter((v) => v !== value)
    }
  }
}

const marks = computed(() => ({ tag: draft.value.tags, repo: draft.value.repos, issue: draft.value.issue_keys }))

const remindLocal = computed({
  get: () => toLocalInput(draft.value.remind_at),
  set: (value) => (draft.value.remind_at = fromLocalInput(value)),
})

const presets = computed(() => reminderPresets())

watch(
  () => store.editor.open,
  async (open) => {
    if (open) {
      trackMentionsOnOpen()
      await nextTick()
      titleInput.value?.focus()
    }
  },
)

async function save() {
  // Pede permissão de notificação no clique (gesto do usuário), só quando precisa.
  if (draft.value.remind_at && typeof Notification !== 'undefined' && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {})
  }
  await store.saveEditor()
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
    <div v-if="store.editor.open" class="editor-backdrop" @mousedown.self="store.closeEditor()">
      <form
        class="editor"
        role="dialog"
        aria-modal="true"
        :aria-label="draft.id ? 'Editar lembrete' : 'Novo lembrete'"
        :style="{ '--note-bg': NOTE_COLORS[draft.color].bg, '--note-border': NOTE_COLORS[draft.color].border }"
        @submit.prevent="save"
        @keydown="onKeydown"
      >
        <header class="editor__header">
          <input
            ref="titleInput"
            v-model="draft.title"
            class="editor__title"
            maxlength="200"
            placeholder="Título"
            aria-label="Título"
          >
          <button type="button" class="editor__icon" :class="{ 'editor__icon--on': draft.pinned }" :title="draft.pinned ? 'Desafixar' : 'Fixar no topo'" @click="draft.pinned = !draft.pinned">
            <Pin :size="16" />
          </button>
          <button type="button" class="editor__icon" title="Fechar (Esc)" @click="store.closeEditor()"><X :size="16" /></button>
        </header>

        <MentionTextarea
          v-model="draft.body"
          class="editor__body"
          rows="7"
          maxlength="20000"
          placeholder="Anote o achado, a correção, o ponto em aberto… #tag, @repositório ou @WAI-1234 (Enter confirma)"
          aria-label="Texto"
          :tags="tagNames"
          :repos="sync.selectedRepos"
          :marks="marks"
          @activate="loadSuggestions"
          @add-tag="(tag) => addMention('tag', tag)"
          @add-repo="(repo) => addMention('repo', repo)"
          @add-issue="(key) => addMention('issue', key)"
          @blur="pruneMentions"
        />

        <div class="field">
          <label class="field__label" for="note-tags">Tags</label>
          <ChipsInput v-model="draft.tags" input-id="note-tags" prefix="#" placeholder="backend, retry…" :normalize="normalizeTag" invalid-message="Tag inválida" />
        </div>

        <div class="field">
          <label class="field__label" for="note-links">Vínculos</label>
          <LinksField
            v-model:issues="draft.issue_keys"
            v-model:repos="draft.repos"
            input-id="note-links"
            :available-repos="sync.selectedRepos"
            @activate="loadSuggestions('@')"
          />
        </div>

        <div class="field">
          <label class="field__label" for="note-remind">Lembrar em</label>
          <div class="editor__remind">
            <input id="note-remind" v-model="remindLocal" type="datetime-local" class="field__input editor__datetime">
            <button v-for="p in presets" :key="p.id" type="button" class="editor__preset" @click="draft.remind_at = p.at.toISOString()">{{ p.label }}</button>
            <button v-if="draft.remind_at" type="button" class="editor__preset" title="Sem lembrete" @click="draft.remind_at = null">
              <BellOff :size="13" />
            </button>
          </div>
        </div>

        <footer class="editor__footer">
          <div class="editor__colors" role="radiogroup" aria-label="Cor">
            <button
              v-for="key in NOTE_COLOR_KEYS"
              :key="key"
              type="button"
              role="radio"
              class="editor__swatch"
              :aria-checked="draft.color === key"
              :title="NOTE_COLORS[key].label"
              :style="{ background: NOTE_COLORS[key].bg, borderColor: NOTE_COLORS[key].border }"
              @click="draft.color = key"
            >
              <Check v-if="draft.color === key" :size="12" />
            </button>
          </div>
          <p v-if="store.editor.error" class="editor__error" role="alert">{{ store.editor.error }}</p>
          <button type="button" class="btn btn--secondary" @click="store.closeEditor()">Cancelar</button>
          <button type="submit" class="btn btn--primary" :disabled="store.editor.saving" title="Ctrl+Enter">
            {{ store.editor.saving ? 'Salvando…' : 'Salvar' }}
          </button>
        </footer>
      </form>
    </div>
  </Teleport>
</template>

<style scoped>
.editor-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: start center;
  padding: 10vh var(--space-4) var(--space-4);
  background: var(--color-overlay);
}

.editor {
  width: min(640px, 100%);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5) var(--space-5);
  border: 1px solid var(--note-border);
  border-top-width: 5px;
  border-radius: var(--radius-xl);
  background: var(--note-bg);
  box-shadow: var(--shadow-modal);
}

.editor__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.editor__title {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  font: inherit;
  font-size: var(--text-lg);
  font-weight: 600;
}

.editor__icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.editor__icon:hover,
.editor__icon--on {
  background: var(--note-scrim);
  color: var(--color-text);
}

.editor__remind {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.editor__datetime {
  width: auto;
}

.editor__preset {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid var(--note-scrim-border);
  border-radius: var(--radius-md);
  background: var(--note-inset);
  font-size: var(--text-xs);
  font-weight: 500;
}

.editor__preset:hover {
  background: var(--note-inset-strong);
}

.editor__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.editor__colors {
  display: flex;
  gap: 6px;
  margin-right: auto;
}

.editor__swatch {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 2px solid;
  border-radius: 50%;
}

.editor__error {
  flex-basis: 100%;
  order: -1;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}
</style>
