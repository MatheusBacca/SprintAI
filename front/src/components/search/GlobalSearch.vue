<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { CornerDownLeft, GitPullRequest, MessageSquare, Search, SquareCheck, StickyNote, X } from 'lucide-vue-next'
import { CONTEXT_KINDS } from '@/constants/contextKinds'
import { NOTE_COLORS } from '@/constants/noteColors'
import { useIssueNavigation } from '@/composables/useIssueNavigation'
import { api } from '@/services/api'
import { useContextsStore } from '@/stores/contexts'
import { useNotesStore } from '@/stores/notes'
import { MIN_QUERY, SEARCH_PERIODS, SEARCH_TYPES, useSearchStore } from '@/stores/search'
import { highlightTerms, searchTerms } from '@/utils/highlight'
import { safeUrl } from '@/utils/safeUrl'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  debounceMs: { type: Number, default: 200 },
})

const search = useSearchStore()
const notes = useNotesStore()
const contexts = useContextsStore()
const { openIssue } = useIssueNavigation()

const input = ref(null)
const list = ref(null)
const active = ref(0)
const openError = ref(null)
let debounce = null
let returnFocus = null

const TYPE_LABEL = Object.fromEntries(SEARCH_TYPES.map((t) => [t.id, t.label]))
const PR_STATE = { OPEN: 'Aberto', MERGED: 'Mergeado', DECLINED: 'Recusado', SUPERSEDED: 'Substituído' }

const terms = computed(() => searchTerms(search.query))
const hits = computed(() => search.hits)
const tooShort = computed(() => search.query.trim().length < MIN_QUERY)
const indexOf = (hit) => hits.value.indexOf(hit)

watch(
  () => search.open,
  async (open) => {
    if (!open) {
      clearTimeout(debounce)
      returnFocus?.focus?.()
      returnFocus = null
      return
    }
    returnFocus = document.activeElement
    openError.value = null
    active.value = 0
    search.run()
    await nextTick()
    input.value?.focus()
    input.value?.select()
  },
  { immediate: true },
)

watch(hits, () => {
  if (active.value >= hits.value.length) active.value = 0
})

function onInput() {
  clearTimeout(debounce)
  debounce = setTimeout(() => {
    active.value = 0
    search.run()
  }, props.debounceMs)
}

async function move(delta) {
  if (!hits.value.length) return
  active.value = (active.value + delta + hits.value.length) % hits.value.length
  await nextTick()
  list.value?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' })
}

async function open(hit) {
  if (!hit) return
  openError.value = null
  try {
    if (hit.type === 'issue') return finish(() => openIssue(hit.id))
    if (hit.type === 'comment') return finish(() => openIssue(hit.issue_key, 'historico'))
    if (hit.type === 'pull_request') {
      if (hit.issue_key && hit.issue_in_mirror) return finish(() => openIssue(hit.issue_key, 'prs'))
      const url = safeUrl(hit.meta.url)
      if (url) window.open(url, '_blank', 'noopener')
      return finish()
    }
    if (hit.type === 'context') {
      if (hit.issue_in_mirror) return finish(() => openIssue(hit.issue_key, 'contextos'))
      const context = await api.get(`/contexts/${hit.id}`)
      return finish(() => contexts.openEditor(context))
    }
    if (hit.type === 'note') {
      const note = await api.get(`/notes/${hit.id}`)
      return finish(() => notes.openEditor(note))
    }
  } catch (error) {
    openError.value = error.message
  }
}

function finish(action) {
  // O destino (painel/editor) recebe o foco; não devolve para onde estava.
  returnFocus = null
  search.close()
  action?.()
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    search.close()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter' && event.target === input.value) {
    event.preventDefault()
    open(hits.value[active.value])
  }
}

function typeCount(id) {
  return id === 'all' ? Object.values(search.totals).reduce((a, b) => a + b, 0) : search.totals[id]
}

function icon(hit) {
  if (hit.type === 'context') return CONTEXT_KINDS[hit.meta.kind]?.icon ?? SquareCheck
  return { issue: SquareCheck, comment: MessageSquare, pull_request: GitPullRequest, note: StickyNote }[hit.type]
}

function iconColor(hit) {
  if (hit.type === 'context') return CONTEXT_KINDS[hit.meta.kind]?.color
  if (hit.type === 'note') return NOTE_COLORS[hit.meta.color]?.accent
  return undefined
}
</script>

<template>
  <Teleport to="body">
    <div v-if="search.open" class="gsearch-backdrop" @mousedown.self="search.close()">
      <div class="gsearch" role="dialog" aria-modal="true" aria-label="Busca global" @keydown="onKeydown">
        <header class="gsearch__bar">
          <Search :size="18" />
          <input
            ref="input"
            v-model="search.query"
            type="search"
            placeholder="Buscar tarefas, comentários, PRs, contextos e lembretes"
            aria-label="Buscar"
            aria-controls="gsearch-results"
            maxlength="200"
            @input="onInput"
          >
          <select :value="search.period" class="gsearch__period" aria-label="Período" @change="search.setPeriod($event.target.value)">
            <option v-for="p in SEARCH_PERIODS" :key="p.id" :value="p.id">{{ p.label }}</option>
          </select>
          <button type="button" class="gsearch__icon" title="Fechar (Esc)" @click="search.close()"><X :size="16" /></button>
        </header>

        <nav class="gsearch__types" aria-label="Tipos">
          <button
            v-for="t in [{ id: 'all', label: 'Tudo' }, ...SEARCH_TYPES]"
            :key="t.id"
            type="button"
            class="gsearch__type"
            :class="{ 'gsearch__type--on': search.type === t.id }"
            @click="search.setType(t.id)"
          >
            {{ t.label }}<small v-if="!tooShort && typeCount(t.id) != null">{{ typeCount(t.id) }}</small>
          </button>
        </nav>

        <p v-if="search.error || openError" class="gsearch__error" role="alert">{{ search.error || openError }}</p>

        <div v-if="tooShort" class="gsearch__hint">
          <p>Digite ao menos {{ MIN_QUERY }} letras.</p>
          <ul>
            <li>Sem acento: <code>integracao</code> acha “Integração”.</li>
            <li>Trecho de palavra: <code>reprocess</code>.</li>
            <li>Chave de tarefa: <code>WAI-8295</code> traz a tarefa, os PRs, contextos e lembretes dela.</li>
          </ul>
        </div>

        <p v-else-if="search.loading && !search.result" class="gsearch__hint">Buscando…</p>

        <div v-else-if="search.result && !search.result.groups.length" class="gsearch__hint">
          <p>Nada encontrado para “{{ search.result.query }}”{{ search.period !== 'any' ? ' neste período' : '' }}.</p>
        </div>

        <div v-else-if="search.result" id="gsearch-results" ref="list" class="gsearch__results" role="listbox" aria-label="Resultados">
          <section v-for="group in search.result.groups" :key="group.type" class="gsearch__group" :data-type="group.type">
            <h3 class="gsearch__group-title">
              {{ TYPE_LABEL[group.type] }} <small>{{ group.total }}</small>
              <button v-if="search.type === 'all' && group.total > group.items.length" type="button" class="gsearch__all" @click="search.setType(group.type)">
                ver todos
              </button>
            </h3>
            <div
              v-for="hit in group.items"
              :key="`${hit.type}:${hit.id}`"
              class="gsearch__hit"
              role="option"
              :aria-selected="indexOf(hit) === active"
              :data-id="hit.id"
              @mousemove="active = indexOf(hit)"
              @click="open(hit)"
            >
              <component :is="icon(hit)" :size="16" class="gsearch__hit-icon" :style="{ color: iconColor(hit) }" />
              <div class="gsearch__hit-main">
                <p class="gsearch__hit-title">
                  <strong v-if="hit.type === 'issue'" class="gsearch__key">{{ hit.id }}</strong>
                  <template v-if="hit.type === 'comment'">
                    <strong class="gsearch__key">{{ hit.issue_key }}</strong> {{ hit.issue_summary }}
                  </template>
                  <template v-else-if="hit.title">
                    <mark v-for="(p, i) in highlightTerms(hit.title, terms)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
                  </template>
                  <span v-else class="gsearch__muted">Sem título</span>
                </p>
                <p v-if="hit.snippet" class="gsearch__snippet">
                  <mark v-for="(p, i) in highlightTerms(hit.snippet, terms)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
                </p>
                <p class="gsearch__meta">
                  <template v-if="hit.type === 'issue'">
                    <span>{{ hit.meta.issue_type }}</span><span class="gsearch__pill">{{ hit.meta.status }}</span>
                  </template>
                  <template v-else-if="hit.type === 'comment'">
                    <span>{{ hit.title }}</span>
                  </template>
                  <template v-else-if="hit.type === 'pull_request'">
                    <span>{{ hit.meta.repo_slug }} #{{ hit.meta.pr_id }}</span>
                    <span class="gsearch__pill" :data-state="hit.meta.state">{{ PR_STATE[hit.meta.state] ?? hit.meta.state }}</span>
                    <span v-if="hit.issue_keys.length">{{ hit.issue_keys.join(', ') }}</span>
                  </template>
                  <template v-else-if="hit.type === 'context'">
                    <span>{{ CONTEXT_KINDS[hit.meta.kind]?.label }}</span>
                    <span v-if="hit.meta.kind === 'open_point'" class="gsearch__pill" :data-state="hit.meta.status">{{ hit.meta.status === 'resolved' ? 'Resolvido' : 'Em aberto' }}</span>
                    <span>{{ hit.issue_key }}</span>
                  </template>
                  <template v-else-if="hit.type === 'note'">
                    <span v-if="hit.meta.archived" class="gsearch__pill">Arquivado</span>
                    <span v-if="hit.issue_keys.length">{{ hit.issue_keys.join(', ') }}</span>
                  </template>
                  <time v-if="hit.occurred_at" :datetime="hit.occurred_at">{{ formatRelative(hit.occurred_at) }}</time>
                </p>
              </div>
              <CornerDownLeft v-if="indexOf(hit) === active" :size="14" class="gsearch__enter" />
            </div>
          </section>
          <button
            v-if="search.type !== 'all' && search.result.groups[0] && search.result.groups[0].items.length < search.result.groups[0].total"
            type="button"
            class="btn btn--secondary gsearch__more"
            :disabled="search.loadingMore"
            @click="search.loadMore()"
          >
            {{ search.loadingMore ? 'Carregando…' : 'Carregar mais' }}
          </button>
        </div>

        <footer class="gsearch__footer">
          <kbd>↑</kbd><kbd>↓</kbd> navegar <kbd>Enter</kbd> abrir <kbd>Esc</kbd> fechar
          <span class="gsearch__footer-note">Busca por palavra-chave · semântica chega na B6</span>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.gsearch-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: start center;
  padding: 9vh var(--space-4) var(--space-4);
  background: var(--color-overlay);
}

.gsearch {
  width: min(760px, 100%);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.gsearch__bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-muted);
}

.gsearch__bar input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  font: inherit;
  font-size: var(--text-md);
  color: var(--color-text);
}

.gsearch__bar input::-webkit-search-cancel-button {
  display: none;
}

.gsearch__period {
  padding: 4px 6px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font: inherit;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.gsearch__icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.gsearch__icon:hover {
  background: var(--color-surface-muted);
}

.gsearch__types {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.gsearch__type {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.gsearch__type small {
  color: var(--color-text-muted);
}

.gsearch__type--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 600;
}

.gsearch__error {
  margin: 0;
  padding: var(--space-2) var(--space-4);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.gsearch__hint {
  padding: var(--space-5) var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.gsearch__hint p {
  margin: 0 0 var(--space-2);
}

.gsearch__hint ul {
  margin: 0;
  padding-left: var(--space-5);
  line-height: 24px;
  color: var(--color-text-muted);
}

.gsearch__hint code {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text);
}

.gsearch__results {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.gsearch__group + .gsearch__group {
  margin-top: var(--space-2);
}

.gsearch__group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: var(--space-2) var(--space-3) 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.gsearch__group-title small {
  font-size: inherit;
  color: var(--color-text-secondary);
}

.gsearch__all {
  margin-left: auto;
  padding: 0;
  border: 0;
  background: none;
  font-size: 11px;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
  color: var(--color-primary);
}

.gsearch__hit {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.gsearch__hit[aria-selected='true'] {
  background: var(--color-primary-soft);
}

.gsearch__hit-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-text-secondary);
}

.gsearch__hit-main {
  flex: 1;
  min-width: 0;
}

.gsearch__hit-title,
.gsearch__snippet,
.gsearch__meta {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gsearch__hit-title {
  font-size: var(--text-sm);
  font-weight: 500;
}

.gsearch__key {
  margin-right: 6px;
  font-weight: 700;
  color: var(--color-primary);
}

.gsearch__muted {
  color: var(--color-text-muted);
}

.gsearch__snippet {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.gsearch__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.gsearch__meta time {
  margin-left: auto;
}

.gsearch__pill {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
  font-weight: 600;
}

.gsearch__pill[data-state='MERGED'],
.gsearch__pill[data-state='resolved'] {
  background: var(--color-success-surface);
  color: var(--color-success);
}

.gsearch__pill[data-state='open'] {
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
}

.gsearch__enter {
  flex-shrink: 0;
  margin-top: 3px;
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

.gsearch__more {
  display: block;
  margin: var(--space-2) auto;
  font-size: var(--text-xs);
}

.gsearch__footer {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: var(--space-2) var(--space-4);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-muted);
  font-size: 11px;
  color: var(--color-text-muted);
}

.gsearch__footer-note {
  margin-left: auto;
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
</style>
