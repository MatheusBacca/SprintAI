<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Search, StickyNote, X } from 'lucide-vue-next'

import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import NoteCard from '@/components/notes/NoteCard.vue'
import { useNotesStore } from '@/stores/notes'
import { useRefreshStore } from '@/stores/refresh'
import { useScreenContextStore } from '@/stores/screenContext'
import { safeUrl } from '@/utils/safeUrl'

const route = useRoute()
const router = useRouter()
const notes = useNotesStore()
const refresh = useRefreshStore()
const screen = useScreenContextStore()

const FILTERS = [
  { id: 'ativos', label: 'Ativos', params: {} },
  { id: 'fixados', label: 'Fixados', params: { pinned: true } },
  { id: 'lembrete', label: 'Com lembrete', params: { due: 'upcoming' } },
  { id: 'vencidos', label: 'Vencidos', params: { due: 'overdue' } },
  { id: 'arquivados', label: 'Arquivados', params: { archived: true } },
]

const q = ref(route.query.q ?? '')
const filter = computed(() => FILTERS.find((f) => f.id === route.query.filtro) ?? FILTERS[0])
const tag = computed(() => route.query.tag ?? null)
const issueKey = computed(() => route.query.tarefa ?? null)

screen.enter('notes')
onBeforeUnmount(() => screen.enter(null))
watch(issueKey, (key) => screen.focusIssue(key), { immediate: true })

function setQuery(patch) {
  const query = { ...route.query, ...patch }
  for (const key of Object.keys(query)) if (query[key] === null || query[key] === '') delete query[key]
  router.replace({ query })
}

let debounce
watch(q, (value) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => setQuery({ q: value.trim() || null }), 250)
})

function reload() {
  notes.list({ q: route.query.q, tag: tag.value, ...filter.value.params, limit: 200 })
}

watch(() => [route.query.q, route.query.filtro, route.query.tag, notes.revision, refresh.revision], reload, { immediate: true })
watch(() => [notes.revision, refresh.revision], () => notes.loadTags())
onMounted(() => notes.loadTags())
watch(() => notes.items, (items) => screen.$patch({ filters: { q: route.query.q, tag: tag.value }, visibleIssueKeys: [...new Set(items.flatMap((n) => n.issues.map((i) => i.key)))] }))

function openIssue(issue) {
  if (issue.in_mirror) setQuery({ tarefa: issue.key })
  else if (safeUrl(issue.url)) window.open(safeUrl(issue.url), '_blank', 'noopener')
}

const pinned = computed(() => notes.items.filter((n) => n.pinned))
const others = computed(() => notes.items.filter((n) => !n.pinned))
</script>

<template>
  <div class="notes-page">
    <section class="notes">
      <header class="notes__header card">
        <div class="notes__top">
          <h1 class="notes__title"><StickyNote :size="20" /> Lembretes</h1>
          <label class="notes__search">
            <Search :size="15" />
            <input v-model="q" type="search" placeholder="Buscar por palavra, tag ou WAI-1234" aria-label="Buscar lembretes">
          </label>
          <button type="button" class="btn btn--primary" @click="notes.openEditor(null, issueKey ? { issue_keys: [issueKey] } : {})">
            <Plus :size="15" /> Novo lembrete
          </button>
        </div>

        <nav class="notes__filters" aria-label="Filtros">
          <button
            v-for="f in FILTERS"
            :key="f.id"
            type="button"
            class="notes__filter"
            :class="{ 'notes__filter--on': filter.id === f.id }"
            @click="setQuery({ filtro: f.id === 'ativos' ? null : f.id })"
          >
            {{ f.label }}
          </button>
          <span class="notes__divider" />
          <button
            v-for="t in notes.tags.slice(0, 12)"
            :key="t.tag"
            type="button"
            class="notes__tag"
            :class="{ 'notes__tag--on': tag === t.tag }"
            @click="setQuery({ tag: tag === t.tag ? null : t.tag })"
          >
            #{{ t.tag }} <small>{{ t.count }}</small>
          </button>
          <button v-if="tag" type="button" class="notes__clear" @click="setQuery({ tag: null })"><X :size="12" /> limpar tag</button>
        </nav>
      </header>

      <p v-if="notes.error" class="notes__error" role="alert">{{ notes.error }}</p>

      <div v-else-if="!notes.loading && !notes.items.length" class="notes__empty card">
        <StickyNote :size="28" />
        <p v-if="route.query.q || tag || filter.id !== 'ativos'">Nenhum lembrete encontrado com esses filtros.</p>
        <p v-else>Anote achados, correções e pontos em aberto para revisitar nas próximas tarefas.</p>
        <button type="button" class="btn btn--primary" @click="notes.openEditor()"><Plus :size="15" /> Criar o primeiro</button>
      </div>

      <template v-else>
        <p class="notes__count">{{ notes.total }} lembrete(s)</p>
        <h2 v-if="pinned.length" class="notes__section">Fixados</h2>
        <div v-if="pinned.length" class="notes__board">
          <NoteCard
            v-for="note in pinned"
            :key="note.id"
            :note="note"
            :highlight="route.query.q ?? ''"
            @edit="notes.openEditor"
            @toggle-pin="(n) => notes.patch(n.id, { pinned: !n.pinned })"
            @toggle-archive="(n) => notes.patch(n.id, { archived: !n.archived })"
            @delete="(n) => notes.remove(n.id)"
            @complete="(n) => notes.acknowledge(n.id)"
            @open-issue="openIssue"
            @select-tag="(t) => setQuery({ tag: t })"
          />
        </div>
        <h2 v-if="pinned.length && others.length" class="notes__section">Outros</h2>
        <div class="notes__board">
          <NoteCard
            v-for="note in others"
            :key="note.id"
            :note="note"
            :highlight="route.query.q ?? ''"
            @edit="notes.openEditor"
            @toggle-pin="(n) => notes.patch(n.id, { pinned: !n.pinned })"
            @toggle-archive="(n) => notes.patch(n.id, { archived: !n.archived })"
            @delete="(n) => notes.remove(n.id)"
            @complete="(n) => notes.acknowledge(n.id)"
            @open-issue="openIssue"
            @select-tag="(t) => setQuery({ tag: t })"
          />
        </div>
      </template>
    </section>

    <IssueDrawer v-if="issueKey" :issue-key="issueKey" @close="setQuery({ tarefa: null })" @open="(k) => setQuery({ tarefa: k })" />
  </div>
</template>

<style scoped>
.notes-page {
  height: 100%;
  display: flex;
  gap: var(--space-4);
}

.notes {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.notes__header {
  padding: var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.notes__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.notes__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.notes__search {
  flex: 1;
  min-width: 220px;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
}

.notes__search:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.notes__search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  font: inherit;
  font-size: var(--text-sm);
}

.notes__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.notes__filter,
.notes__tag,
.notes__clear {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.notes__filter--on,
.notes__tag--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 600;
}

.notes__tag small {
  color: var(--color-text-muted);
}

.notes__clear {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border-style: dashed;
}

.notes__divider {
  width: 1px;
  height: 18px;
  margin: 0 4px;
  background: var(--color-border);
}

.notes__count,
.notes__section {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.notes__board {
  columns: 280px auto;
  column-gap: var(--space-4);
}

.notes__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-6);
  color: var(--color-text-secondary);
  text-align: center;
}

.notes__empty p {
  margin: 0;
}

.notes__error {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
}
</style>
