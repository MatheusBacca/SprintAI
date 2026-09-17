<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Check, FolderGit2, SquareCheck, X } from 'lucide-vue-next'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'
import { ISSUE_KEY, fold } from '@/utils/noteTokens'

/**
 * "Vínculos" do lembrete num campo só: tarefas (roxo) e repositórios (azul), como
 * chips, e a busca no mesmo campo. Os repositórios sugeridos são os acompanhados pelo
 * dev; as tarefas vêm do espelho, casando qualquer campo visível (quem filtra é o back).
 *
 * Enter marca a linha ativa; chave inteira digitada (ou várias coladas) vale ela mesma
 * — "WAI-9" não pode virar a WAI-9001 do topo da lista, e tarefa fora do espelho só
 * entra assim. A lista só busca quando o campo é usado: abrir o editor não custa request.
 */
const props = defineProps({
  issues: { type: Array, required: true },
  repos: { type: Array, required: true },
  /** Repositórios acompanhados pelo dev (sugestão). */
  availableRepos: { type: Array, default: () => [] },
  inputId: { type: String, default: undefined },
})
const emit = defineEmits(['update:issues', 'update:repos', 'activate'])

const LIMIT = 30
const MAX_REPOS = 5
const DEBOUNCE_MS = 200
const SEPARATOR = /[,;\s]+/

const q = ref('')
const open = ref(false)
const loading = ref(false)
const error = ref(null)
// Chave digitada inválida: fica embaixo do campo, sem esconder a lista.
const keyError = ref(null)
const tasks = ref([])
const active = ref(0)
// Título das tarefas já vistas na lista, para o chip explicar o que é no hover.
const summaries = ref({})
const listId = `links-${Math.random().toString(36).slice(2, 8)}`

let timer = null
let requestId = 0

const selected = computed(() => ({ issue: new Set(props.issues), repo: new Set(props.repos) }))

const items = computed(() => {
  const needle = fold(q.value.trim())
  const repos = props.availableRepos
    .filter((r) => fold(r).includes(needle))
    .slice(0, MAX_REPOS)
    .map((r) => ({ kind: 'repo', value: r, label: r, hint: 'repositório' }))
  const issues = tasks.value.map((t) => ({ kind: 'issue', value: t.key, label: t.summary, hint: t.status, category: t.status_category }))
  return [...repos, ...issues]
})

async function load() {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    const result = await api.get(`/issues${toQuery({ q: q.value.trim(), limit: LIMIT })}`)
    if (id !== requestId) return
    tasks.value = Array.isArray(result) ? result : []
    for (const t of tasks.value) summaries.value[t.key] = t.summary
    active.value = 0
  } catch (e) {
    if (id === requestId) error.value = e.message
  } finally {
    if (id === requestId) loading.value = false
  }
}

function onFocus() {
  open.value = true
  emit('activate')
  load()
}

function onInput() {
  keyError.value = null
  open.value = true
  active.value = 0
  clearTimeout(timer)
  timer = setTimeout(load, DEBOUNCE_MS)
}

function toggle(item) {
  const [list, event] = item.kind === 'repo' ? [props.repos, 'update:repos'] : [props.issues, 'update:issues']
  emit(event, selected.value[item.kind].has(item.value) ? list.filter((v) => v !== item.value) : [...list, item.value])
}

function addTypedKeys() {
  const parts = q.value.split(SEPARATOR).map((p) => p.trim().toUpperCase()).filter(Boolean)
  emit('update:issues', [...props.issues, ...parts.filter((p) => !selected.value.issue.has(p))])
  q.value = ''
  keyError.value = null
}

function removeIssue(key) {
  emit('update:issues', props.issues.filter((k) => k !== key))
}

function removeRepo(repo) {
  emit('update:repos', props.repos.filter((r) => r !== repo))
}

function onKeydown(event) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    open.value = true
    const total = items.value.length
    if (total) active.value = (active.value + (event.key === 'ArrowDown' ? 1 : -1) + total) % total
  } else if (event.key === 'Enter') {
    // Enter aqui vincula; não pode salvar o lembrete (o form faz submit no Enter).
    event.preventDefault()
    const parts = q.value.split(SEPARATOR).filter(Boolean)
    if (parts.length && parts.every((p) => ISSUE_KEY.test(p.toUpperCase()))) return addTypedKeys()
    const item = open.value ? items.value[active.value] : null
    if (item) toggle(item)
    else if (q.value.trim()) keyError.value = `Nada para vincular com "${q.value.trim()}": escolha na lista ou digite uma chave (WAI-1234).`
  } else if (event.key === 'Backspace' && !q.value) {
    // Apaga o último chip mostrado: repositórios vêm depois das tarefas.
    if (props.repos.length) removeRepo(props.repos.at(-1))
    else if (props.issues.length) removeIssue(props.issues.at(-1))
  } else if (event.key === 'Escape' && open.value) {
    // Primeiro Esc fecha só a lista; o segundo chega ao editor e fecha o lembrete.
    event.stopPropagation()
    open.value = false
  }
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="links">
    <div class="links__box" :class="{ 'links__box--error': keyError }">
      <span v-for="key in issues" :key="`issue:${key}`" class="links__chip" data-kind="issue" :title="summaries[key]">
        <SquareCheck :size="12" />
        {{ key }}
        <button type="button" :aria-label="`Desvincular ${key}`" @click="removeIssue(key)"><X :size="12" /></button>
      </span>
      <span v-for="repo in repos" :key="`repo:${repo}`" class="links__chip" data-kind="repo" title="Repositório">
        <FolderGit2 :size="12" />
        {{ repo }}
        <button type="button" :aria-label="`Desvincular ${repo}`" @click="removeRepo(repo)"><X :size="12" /></button>
      </span>
      <input
        :id="inputId"
        v-model="q"
        class="links__input"
        type="text"
        role="combobox"
        autocomplete="off"
        :placeholder="issues.length || repos.length ? 'Buscar mais…' : 'Buscar tarefa (título, WAI-1234, status…) ou repositório'"
        aria-label="Buscar tarefa ou repositório para vincular"
        :aria-expanded="open"
        :aria-controls="listId"
        @focus="onFocus"
        @blur="open = false"
        @input="onInput"
        @keydown="onKeydown"
      >
    </div>

    <!-- mousedown.prevent: clicar numa linha não tira o foco da busca (que fecharia a lista). -->
    <ul v-if="open" :id="listId" class="links__list" role="listbox" aria-multiselectable="true" @mousedown.prevent>
      <li v-if="error && !items.length" class="links__empty" role="alert">{{ error }}</li>
      <li v-else-if="!items.length" class="links__empty">
        {{ loading ? 'Buscando…' : 'Nada encontrado. Uma chave válida + Enter vincula mesmo assim.' }}
      </li>
      <li
        v-for="(item, i) in items"
        v-else
        :key="`${item.kind}:${item.value}`"
        class="links__item"
        :class="{ 'links__item--active': i === active }"
        role="option"
        :aria-selected="selected[item.kind].has(item.value)"
        :data-kind="item.kind"
        :data-key="item.value"
        @mouseenter="active = i"
        @click="toggle(item)"
      >
        <span class="links__check" :class="{ 'links__check--on': selected[item.kind].has(item.value) }">
          <Check v-if="selected[item.kind].has(item.value)" :size="12" />
        </span>
        <FolderGit2 v-if="item.kind === 'repo'" :size="14" class="links__icon" />
        <span v-else class="links__key">{{ item.value }}</span>
        <span class="links__summary" :title="item.label">{{ item.label }}</span>
        <span class="links__status" :data-category="item.category">{{ item.hint }}</span>
      </li>
    </ul>
    <p v-if="keyError" class="links__error" role="alert">{{ keyError }}</p>
  </div>
</template>

<style scoped>
.links {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.links__box {
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

.links__box:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.links__box--error {
  border-color: var(--color-error);
}

/* Tarefa em roxo, repositório em azul — as mesmas cores das menções no texto. */
.links__chip {
  --chip-color: var(--color-primary);
  --chip-bg: var(--color-primary-soft);
  --chip-hover: var(--color-chip);

  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px 2px 8px;
  border-radius: 999px;
  background: var(--chip-bg);
  color: var(--chip-color);
  font-size: var(--text-xs);
  font-weight: 600;
}

.links__chip[data-kind='repo'] {
  --chip-color: var(--color-repo);
  --chip-bg: var(--color-repo-soft);
  --chip-hover: var(--color-repo-mark);
}

.links__chip button {
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

.links__chip button:hover {
  background: var(--chip-hover);
}

.links__input {
  flex: 1;
  min-width: 160px;
  border: 0;
  outline: 0;
  background: transparent;
  font: inherit;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.links__list {
  max-height: 260px;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-md);
}

.links__empty {
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  text-align: center;
}

.links__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  cursor: pointer;
}

.links__item--active {
  background: var(--color-surface-hover);
}

.links__check {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--color-border-strong);
  border-radius: 4px;
  color: var(--color-on-primary);
}

.links__check--on {
  border-color: var(--color-primary);
  background: var(--color-primary);
}

.links__item[data-kind='repo'] .links__check--on {
  border-color: var(--color-repo);
  background: var(--color-repo);
}

.links__key {
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.links__icon {
  flex-shrink: 0;
  color: var(--color-repo);
}

.links__item[data-kind='repo'] .links__summary {
  font-weight: 600;
  color: var(--color-repo);
}

.links__summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.links__status {
  flex-shrink: 0;
  max-width: 34%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--color-text-muted);
}

.links__status[data-category='done'] {
  color: var(--color-success);
}

.links__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
