<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { FolderGit2, Hash, SquareCheck } from 'lucide-vue-next'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'
import { ISSUE_KEY, fold, mentionParts, normalizeTag } from '@/utils/noteTokens'

/**
 * Texto do lembrete com `#tag` e `@menção`.
 *
 * Digitar `#` ou `@` no começo de uma palavra abre a sugestão; o termo segue até o
 * **Enter**, e por isso aceita espaço — "#boas praticas" vira a tag `boas-praticas`,
 * igual ao campo de Tags. Sem Enter o texto fica só texto. `@` sugere os repositórios
 * acompanhados e as tarefas do dev; a escolhida entra no campo correspondente do
 * lembrete (evento) e o trecho digitado vira o token normalizado no texto.
 *
 * As menções que são vínculo do lembrete (`marks`) ganham fundo colorido: um espelho
 * do texto atrás do textarea transparente pinta só o fundo dos trechos — textarea não
 * aceita marcação, e trocar por contenteditable traria HTML para dentro do lembrete.
 */
defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: String, required: true },
  /** Tags já usadas em lembretes (sugestão do `#`). */
  tags: { type: Array, default: () => [] },
  /** Repositórios acompanhados pelo dev (sugestão do `@`). */
  repos: { type: Array, default: () => [] },
  /** Vínculos atuais do lembrete (`{ tag, issue, repo }`): as menções deles são pintadas. */
  marks: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'add-tag', 'add-repo', 'add-issue', 'activate', 'blur'])

const MAX_QUERY = 60
const MAX_OPTIONS = 8
const DEBOUNCE_MS = 150
const ICONS = { tag: Hash, repo: FolderGit2, issue: SquareCheck }

const textarea = ref(null)
const backdrop = ref(null)
const parts = computed(() => mentionParts(props.modelValue, props.marks))
// { char: '#' | '@', start } — posição do gatilho no texto
const trigger = ref(null)
const query = ref('')
const options = ref([])
const active = ref(0)
const listId = `mention-${Math.random().toString(36).slice(2, 8)}`

let timer = null
let requestId = 0
let issues = []

function close() {
  trigger.value = null
  options.value = []
  clearTimeout(timer)
  requestId += 1
}

function tagOptions() {
  const typed = normalizeTag(query.value)
  const needle = typed ?? ''
  const existing = props.tags.filter((t) => t !== typed && fold(t).includes(fold(needle)))
  const literal = typed ? [{ kind: 'tag', value: typed, hint: props.tags.includes(typed) ? 'tag existente' : 'nova tag' }] : []
  return [...literal, ...existing.map((t) => ({ kind: 'tag', value: t, hint: 'tag existente' }))].slice(0, MAX_OPTIONS)
}

function mentionOptions() {
  const needle = fold(query.value.trim())
  const repos = props.repos.filter((r) => fold(r).includes(needle)).map((r) => ({ kind: 'repo', value: r, hint: 'repositório' }))
  const key = query.value.trim().toUpperCase()
  // Chave inteira digitada entra mesmo antes da busca voltar (ou fora das minhas).
  const typedKey = ISSUE_KEY.test(key) && !issues.some((i) => i.key === key) ? [{ kind: 'issue', value: key, hint: 'chave' }] : []
  const found = issues.map((i) => ({ kind: 'issue', value: i.key, hint: i.summary }))
  return [...typedKey, ...repos, ...found].slice(0, MAX_OPTIONS)
}

function rebuild() {
  if (!trigger.value) return
  options.value = trigger.value.char === '#' ? tagOptions() : mentionOptions()
  if (active.value >= options.value.length) active.value = 0
}

function searchIssues() {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    const id = ++requestId
    try {
      const result = await api.get(`/issues${toQuery({ q: query.value.trim(), mine: true, limit: 6 })}`)
      if (id !== requestId || !trigger.value) return
      issues = Array.isArray(result) ? result : []
      rebuild()
    } catch {
      // Sem a lista, o `@` continua sugerindo repositórios e a chave digitada.
    }
  }, DEBOUNCE_MS)
}

/** Recalcula o termo a partir do cursor; fecha se o cursor saiu do trecho. */
function refresh() {
  const el = textarea.value
  if (!trigger.value || !el) return
  const { char, start } = trigger.value
  const caret = el.selectionStart
  const text = el.value
  if (text[start] !== char || caret <= start || el.selectionEnd !== caret) return close()
  const typed = text.slice(start + 1, caret)
  if (typed.includes('\n') || typed.length > MAX_QUERY) return close()
  const changed = typed !== query.value
  query.value = typed
  rebuild()
  if (char === '@' && changed) searchIssues()
}

function open(char, start) {
  trigger.value = { char, start }
  query.value = ''
  active.value = 0
  issues = []
  emit('activate', char)
  rebuild()
  if (char === '@') searchIssues()
}

function onInput(event) {
  emit('update:modelValue', event.target.value)
  const el = event.target
  const caret = el.selectionStart
  const typedChar = event.data === '#' || event.data === '@' ? event.data : null
  // Só abre no começo de uma palavra: "a#b" e e-mail ("dev@weon") ficam texto.
  if (typedChar && (caret === 1 || /\s/.test(el.value[caret - 2]))) open(typedChar, caret - 1)
  else refresh()
}

async function commit(option) {
  const el = textarea.value
  const { char, start } = trigger.value
  const caret = el.selectionStart
  const token = `${char}${option.value} `
  const text = el.value
  emit('update:modelValue', text.slice(0, start) + token + text.slice(caret))
  emit(`add-${option.kind}`, option.value)
  close()
  await nextTick()
  const position = start + token.length
  el.setSelectionRange(position, position)
}

function onKeydown(event) {
  if (!trigger.value || !options.value.length) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const total = options.value.length
    active.value = (active.value + (event.key === 'ArrowDown' ? 1 : -1) + total) % total
  } else if (event.key === 'Enter' && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
    event.preventDefault()
    commit(options.value[active.value])
  } else if (event.key === 'Escape') {
    // Esc cancela a sugestão, não fecha o lembrete.
    event.stopPropagation()
    close()
  }
}

// O espelho rola junto: sem isto as marcas descolam do texto quando ele passa da altura.
function syncScroll() {
  if (backdrop.value && textarea.value) backdrop.value.scrollTop = textarea.value.scrollTop
}

function onBlur() {
  close()
  emit('blur')
}

onBeforeUnmount(() => clearTimeout(timer))
defineExpose({ textarea })
</script>

<template>
  <div class="mention">
    <!-- Espelho do texto: mesma caixa e fonte do textarea, texto invisível, só o fundo das
         menções aparece. Numa linha só: espaço do template viraria texto e desalinharia as
         marcas. O "\n" final dá altura à última linha vazia, como no textarea. -->
    <!-- eslint-disable-next-line vue/max-attributes-per-line, vue/singleline-html-element-content-newline -->
    <div ref="backdrop" class="mention__backdrop" aria-hidden="true"><template v-for="(part, i) in parts" :key="i"><mark v-if="part.kind" class="mention__mark" :data-kind="part.kind">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template>{{ '\n' }}</div>
    <textarea
      ref="textarea"
      v-bind="$attrs"
      class="mention__field"
      :value="modelValue"
      role="combobox"
      aria-autocomplete="list"
      :aria-expanded="Boolean(trigger && options.length)"
      :aria-controls="listId"
      @input="onInput"
      @keydown="onKeydown"
      @click="refresh"
      @keyup.left="refresh"
      @keyup.right="refresh"
      @scroll="syncScroll"
      @blur="onBlur"
    />

    <!-- mousedown.prevent: escolher com o mouse não tira o foco do texto. -->
    <ul v-if="trigger && options.length" :id="listId" class="mention__list" role="listbox" @mousedown.prevent>
      <li class="mention__help">
        {{ trigger.char === '#' ? 'Tag' : 'Repositório ou tarefa sua' }} · Enter adiciona · Esc cancela
      </li>
      <li
        v-for="(option, i) in options"
        :key="`${option.kind}:${option.value}`"
        class="mention__item"
        :class="{ 'mention__item--active': i === active }"
        role="option"
        :aria-selected="i === active"
        :data-kind="option.kind"
        @mouseenter="active = i"
        @click="commit(option)"
      >
        <component :is="ICONS[option.kind]" :size="14" class="mention__icon" />
        <span class="mention__value" :data-kind="option.kind">{{ trigger.char }}{{ option.value }}</span>
        <span class="mention__hint">{{ option.hint }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.mention {
  position: relative;
}

/* Espelho e textarea precisam quebrar linha no mesmo ponto: mesma caixa, fonte,
   espaçamento e calha da barra de rolagem. */
.mention__backdrop,
.mention__field {
  box-sizing: border-box;
  margin: 0;
  padding: var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font: inherit;
  font-size: var(--text-sm);
  line-height: 21px;
  letter-spacing: normal;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  scrollbar-gutter: stable;
}

.mention__backdrop {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--note-inset);
  color: transparent;
  pointer-events: none;
}

.mention__mark {
  border-radius: 3px;
  background: var(--note-scrim);
  box-shadow: 0 0 0 1px var(--note-scrim);
  color: transparent;
}

.mention__mark[data-kind='issue'] {
  background: var(--color-mark);
  box-shadow: 0 0 0 1px var(--color-mark);
}

.mention__mark[data-kind='repo'] {
  background: var(--color-repo-mark);
  box-shadow: 0 0 0 1px var(--color-repo-mark);
}

.mention__field {
  position: relative;
  display: block;
  width: 100%;
  resize: vertical;
  overflow-y: auto;
  border-color: var(--note-scrim-border);
  background: transparent;
  color: var(--color-text);
}

.mention__field:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.mention__list {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 2;
  max-height: 260px;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.mention__help {
  padding: 4px 8px 6px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.mention__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  cursor: pointer;
}

.mention__item--active {
  background: var(--color-surface-hover);
}

.mention__icon {
  flex-shrink: 0;
  color: var(--color-text-muted);
}

.mention__value {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--color-text);
}

.mention__value[data-kind='issue'] {
  color: var(--color-primary);
}

.mention__value[data-kind='repo'] {
  color: var(--color-repo);
}

.mention__hint {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
