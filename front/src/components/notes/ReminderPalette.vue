<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { BellRing, CornerDownLeft, LayoutGrid, Plus, Search, StickyNote, TextSelect, X } from 'lucide-vue-next'
import { NOTE_COLORS } from '@/constants/noteColors'
import { useNotesStore } from '@/stores/notes'
import { useScreenContextStore } from '@/stores/screenContext'
import { formatDateTime } from '@/utils/datetime'
import { highlightParts, snippetAround } from '@/utils/highlight'
import { anyWordQuery, issueKeysIn } from '@/utils/shortcuts'

const props = defineProps({
  debounceMs: { type: Number, default: 180 },
})

const RESULT_LIMIT = 20

const router = useRouter()
const notes = useNotesStore()
const screen = useScreenContextStore()

const input = ref(null)
const list = ref(null)
const query = ref('')
const source = ref(null)
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref(null)
const anyWord = ref(false)
const active = ref(0)
let requestId = 0
let debounce = null
let returnFocus = null

const term = computed(() => query.value.trim())

async function search() {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    let result = await notes.fetch({ q: term.value, limit: RESULT_LIMIT })
    let fallback = false
    // Seleção longa raramente tem todas as palavras numa nota: tenta "qualquer palavra".
    const orQuery = !result.total && anyWordQuery(term.value)
    if (orQuery) {
      result = await notes.fetch({ q: orQuery, limit: RESULT_LIMIT })
      fallback = result.total > 0
    }
    if (id !== requestId) return
    items.value = result.items
    total.value = result.total
    anyWord.value = fallback
    active.value = 0
  } catch (e) {
    if (id === requestId) error.value = e.message
  } finally {
    if (id === requestId) loading.value = false
  }
}

watch(
  () => notes.palette.open,
  async (open) => {
    if (!open) {
      clearTimeout(debounce)
      requestId++
      returnFocus?.focus?.()
      returnFocus = null
      return
    }
    returnFocus = document.activeElement
    query.value = notes.palette.query
    source.value = notes.palette.source
    items.value = []
    search()
    await nextTick()
    input.value?.focus()
    input.value?.select()
  },
  { immediate: true },
)

function onInput() {
  source.value = null
  clearTimeout(debounce)
  debounce = setTimeout(search, props.debounceMs)
}

// Salvou/excluiu em outro lugar (ex.: editor aberto a partir daqui) com a modal aberta.
watch(
  () => notes.revision,
  () => notes.palette.open && search(),
)

function close() {
  notes.closePalette()
}

function openNote(note) {
  if (!note) return
  returnFocus = null // o foco vai para o editor
  close()
  notes.openEditor(note)
}

function createNote() {
  const text = term.value
  const keys = issueKeysIn(text)
  const onlyKey = keys.length === 1 && text.toUpperCase() === keys[0]
  const issueKeys = [...new Set([...keys, screen.focusedIssueKey].filter(Boolean))]
  returnFocus = null
  close()
  notes.openEditor(null, { body: onlyKey ? '' : text, issue_keys: issueKeys })
}

function goToBoard() {
  close()
  router.push({ name: 'notes', query: term.value ? { q: term.value } : {} })
}

async function move(delta) {
  if (!items.value.length) return
  active.value = (active.value + delta + items.value.length) % items.value.length
  await nextTick()
  list.value?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' })
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    close()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    createNote()
  } else if (event.key === 'Enter' && event.target === input.value) {
    // Enter num botão do rodapé aciona o botão, não a nota ativa.
    event.preventDefault()
    openNote(items.value[active.value])
  }
}

function reminderLabel(note) {
  if (!note.remind_at) return null
  if (note.reminder_due) return { tone: 'due', text: `Venceu · ${formatDateTime(note.remind_at)}` }
  if (note.reminded_at) return { tone: 'done', text: `Visto · ${formatDateTime(note.remind_at)}` }
  return { tone: 'upcoming', text: formatDateTime(note.remind_at) }
}

const sourceLabel = computed(
  () => ({ selection: 'Da seleção', issue: 'Tarefa aberta' })[source.value] ?? null,
)
</script>

<template>
  <Teleport to="body">
    <div v-if="notes.palette.open" class="palette-backdrop" @mousedown.self="close">
      <div class="palette" role="dialog" aria-modal="true" aria-label="Buscar lembretes" @keydown="onKeydown">
        <header class="palette__search">
          <Search :size="18" />
          <input
            ref="input"
            v-model="query"
            type="search"
            placeholder="Buscar lembretes por palavra, tag ou WAI-1234"
            aria-label="Buscar lembretes"
            aria-controls="palette-results"
            maxlength="200"
            @input="onInput"
          >
          <span v-if="sourceLabel" class="palette__source" :title="source === 'selection' ? 'Termo vindo do texto selecionado na tela' : undefined">
            <TextSelect :size="12" /> {{ sourceLabel }}
          </span>
          <button type="button" class="palette__icon" title="Fechar (Esc)" @click="close"><X :size="16" /></button>
        </header>

        <p v-if="anyWord" class="palette__hint">Nenhum lembrete com todas as palavras — mostrando os que têm alguma delas.</p>
        <p v-if="error" class="palette__error" role="alert">{{ error }}</p>

        <ul v-if="items.length" id="palette-results" ref="list" class="palette__results" role="listbox" aria-label="Lembretes">
          <li
            v-for="(note, index) in items"
            :key="note.id"
            class="palette__item"
            role="option"
            :aria-selected="index === active"
            :data-id="note.id"
            :style="{ '--note-border': (NOTE_COLORS[note.color] ?? NOTE_COLORS.yellow).border }"
            @mousemove="active = index"
            @click="openNote(note)"
          >
            <div class="palette__item-main">
              <p class="palette__item-title">
                <template v-if="note.title">
                  <mark v-for="(p, i) in highlightParts(note.title, anyWord ? '' : term)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
                </template>
                <span v-else class="palette__untitled">Sem título</span>
              </p>
              <p v-if="note.body" class="palette__item-body">
                <mark v-for="(p, i) in highlightParts(snippetAround(note.body, term), anyWord ? '' : term)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
              </p>
              <p class="palette__item-meta">
                <span v-if="note.pinned" class="palette__pill">Fixado</span>
                <span v-if="reminderLabel(note)" class="palette__reminder" :data-tone="reminderLabel(note).tone">
                  <BellRing :size="11" /> {{ reminderLabel(note).text }}
                </span>
                <span v-for="issue in note.issues" :key="issue.key" class="palette__pill palette__pill--issue">{{ issue.key }}</span>
                <span v-for="tag in note.tags" :key="tag" class="palette__tag">#{{ tag }}</span>
              </p>
            </div>
            <CornerDownLeft v-if="index === active" :size="14" class="palette__enter" />
          </li>
        </ul>

        <p v-else-if="loading" class="palette__loading">Buscando…</p>

        <div v-else-if="!error" class="palette__empty">
          <StickyNote :size="24" />
          <p v-if="term">Nenhum lembrete com “{{ term }}”.</p>
          <p v-else>Nenhum lembrete ainda.</p>
        </div>

        <footer class="palette__footer">
          <span class="palette__keys">
            <kbd>↑</kbd><kbd>↓</kbd> navegar <kbd>Enter</kbd> abrir <kbd>Ctrl</kbd><kbd>Enter</kbd> novo <kbd>Esc</kbd> fechar
          </span>
          <span v-if="total > items.length" class="palette__more">+{{ total - items.length }}</span>
          <button type="button" class="btn btn--secondary palette__btn" @click="goToBoard"><LayoutGrid :size="14" /> Ver no mural</button>
          <button type="button" class="btn btn--primary palette__btn" @click="createNote"><Plus :size="14" /> Novo lembrete</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.palette-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: start center;
  padding: 12vh var(--space-4) var(--space-4);
  background: var(--color-overlay);
}

.palette {
  width: min(680px, 100%);
  max-height: 72vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.palette__search {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-muted);
}

.palette__search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  font: inherit;
  font-size: var(--text-md);
  color: var(--color-text);
}

/* Esc e o X do cabeçalho já fecham; o limpar nativo do campo seria um segundo X. */
.palette__search input::-webkit-search-cancel-button {
  display: none;
}

.palette__loading {
  margin: 0;
  padding: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  text-align: center;
}

.palette__source {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 600;
}

.palette__icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.palette__icon:hover {
  background: var(--color-surface-muted);
}

.palette__hint,
.palette__error {
  margin: 0;
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background: var(--color-surface-muted);
}

.palette__error {
  color: var(--color-error);
  background: var(--color-error-surface);
}

.palette__results {
  flex: 1;
  overflow-y: auto;
  margin: 0;
  padding: var(--space-2);
  list-style: none;
}

.palette__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-left: 3px solid var(--note-border);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.palette__item[aria-selected='true'] {
  background: var(--color-primary-soft);
}

.palette__item-main {
  flex: 1;
  min-width: 0;
}

.palette__item-title,
.palette__item-body,
.palette__item-meta {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.palette__item-title {
  font-size: var(--text-sm);
  font-weight: 600;
}

.palette__untitled {
  color: var(--color-text-muted);
  font-weight: 500;
}

.palette__item-body {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.palette__item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 11px;
}

.palette__pill {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
  font-weight: 600;
}

.palette__pill--issue {
  border: 1px solid var(--color-border);
  background: none;
}

.palette__tag {
  color: var(--color-text-muted);
}

.palette__reminder {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--color-text-secondary);
  font-weight: 600;
}

.palette__reminder[data-tone='due'] {
  color: var(--color-error);
}

.palette__reminder[data-tone='done'] {
  color: var(--color-text-muted);
  font-weight: 500;
}

.palette__enter {
  flex-shrink: 0;
  color: var(--color-primary);
}

mark {
  background: none;
  color: inherit;
}

mark.hit {
  border-radius: 3px;
  background: var(--color-mark);
}

.palette__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-6) var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.palette__empty p {
  margin: 0;
}

.palette__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-muted);
}

.palette__keys {
  margin-right: auto;
  font-size: 11px;
  color: var(--color-text-muted);
}

.palette__more {
  font-size: 11px;
  color: var(--color-text-muted);
}

kbd {
  display: inline-block;
  min-width: 18px;
  margin: 0 2px;
  padding: 0 4px;
  border: 1px solid var(--color-border-strong);
  border-bottom-width: 2px;
  border-radius: 4px;
  background: var(--color-surface);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 16px;
  text-align: center;
  color: var(--color-text-secondary);
}

.palette__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  font-size: var(--text-xs);
}

</style>
