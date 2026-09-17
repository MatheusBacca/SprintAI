<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpenText, Plus, Search } from 'lucide-vue-next'

import ContextCard from '@/components/contexts/ContextCard.vue'
import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import { CONTEXT_KINDS } from '@/constants/contextKinds'
import { useContextsStore } from '@/stores/contexts'
import { useRefreshStore } from '@/stores/refresh'
import { useScreenContextStore } from '@/stores/screenContext'
import { safeUrl } from '@/utils/safeUrl'

const route = useRoute()
const router = useRouter()
const contexts = useContextsStore()
const refresh = useRefreshStore()
const screen = useScreenContextStore()

const FILTERS = [
  { id: 'abertos', label: 'Pontos em aberto', params: { kind: ['open_point'], status: 'open' }, count: (c) => c?.open_points },
  { id: 'todos', label: 'Todos', params: {}, count: (c) => (c ? Object.values(c.by_kind).reduce((a, b) => a + b, 0) : null) },
  ...['finding', 'fix', 'decision', 'summary'].map((kind) => ({
    id: kind,
    label: CONTEXT_KINDS[kind].plural,
    params: { kind: [kind] },
    count: (c) => c?.by_kind[kind] ?? 0,
  })),
  { id: 'resolvidos', label: 'Resolvidos', params: { kind: ['open_point'], status: 'resolved' }, count: () => null },
]

const q = ref(route.query.q ?? '')
const filter = computed(() => FILTERS.find((f) => f.id === route.query.filtro) ?? FILTERS[0])
const issueKey = computed(() => route.query.tarefa ?? null)

screen.enter('contexts')
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

watch(
  () => [route.query.q, route.query.filtro, contexts.revision, refresh.revision],
  () => contexts.list({ q: route.query.q, ...filter.value.params, limit: 200 }),
  { immediate: true },
)
watch(() => [contexts.revision, refresh.revision], () => contexts.loadCounts())
onMounted(() => contexts.loadCounts())

// Agrupa por tarefa de origem, na ordem em que aparecem (a ordem da API já prioriza).
const groups = computed(() => {
  const map = new Map()
  for (const c of contexts.items) {
    if (!map.has(c.issue.key)) map.set(c.issue.key, { issue: c.issue, items: [] })
    map.get(c.issue.key).items.push(c)
  }
  return [...map.values()]
})

watch(groups, (list) => screen.$patch({ filters: { q: route.query.q, filtro: filter.value.id }, visibleIssueKeys: list.map((g) => g.issue.key) }))

function openIssue(issue) {
  if (issue.in_mirror) setQuery({ tarefa: issue.key })
  else if (safeUrl(issue.url)) window.open(safeUrl(issue.url), '_blank', 'noopener')
}

function newContext() {
  const kind = filter.value.params.kind?.length === 1 && filter.value.id !== 'resolvidos' ? filter.value.params.kind[0] : 'finding'
  contexts.openEditor(null, { kind, issue_key: issueKey.value ?? '' })
}

function resolve(context) {
  contexts.openResolver(context, issueKey.value && issueKey.value !== context.issue.key ? issueKey.value : '')
}
</script>

<template>
  <div class="contexts-page">
    <section class="contexts">
      <header class="contexts__header card">
        <div class="contexts__top">
          <h1 class="contexts__title"><BookOpenText :size="20" /> Contextos</h1>
          <label class="contexts__search">
            <Search :size="15" />
            <input v-model="q" type="search" placeholder="Buscar por palavra, tag ou WAI-1234" aria-label="Buscar contextos">
          </label>
          <button type="button" class="btn btn--primary" @click="newContext"><Plus :size="15" /> Novo contexto</button>
        </div>
        <nav class="contexts__filters" aria-label="Filtros">
          <button
            v-for="f in FILTERS"
            :key="f.id"
            type="button"
            class="contexts__filter"
            :class="{ 'contexts__filter--on': filter.id === f.id }"
            @click="setQuery({ filtro: f.id === 'abertos' ? null : f.id })"
          >
            {{ f.label }}<small v-if="f.count(contexts.counts) != null">{{ f.count(contexts.counts) }}</small>
          </button>
        </nav>
      </header>

      <p v-if="contexts.error" class="contexts__error" role="alert">{{ contexts.error }}</p>

      <div v-else-if="!contexts.loading && !contexts.items.length" class="contexts__empty card">
        <BookOpenText :size="28" />
        <p v-if="route.query.q">Nenhum contexto com “{{ route.query.q }}” neste filtro.</p>
        <p v-else-if="filter.id === 'abertos'">Nenhum ponto em aberto.</p>
        <p v-else>Nada registrado aqui ainda. Abra uma tarefa (Sprints) e use a aba Contextos, ou crie direto.</p>
        <button type="button" class="btn btn--primary" @click="newContext"><Plus :size="15" /> Novo contexto</button>
      </div>

      <template v-else>
        <p class="contexts__count">{{ contexts.total }} contexto(s) em {{ groups.length }} tarefa(s)</p>
        <section v-for="group in groups" :key="group.issue.key" class="contexts__group" :data-issue="group.issue.key">
          <h2 class="contexts__group-title">
            <button
              type="button"
              class="contexts__group-key"
              :class="{ 'contexts__group-key--external': !group.issue.in_mirror }"
              :aria-current="issueKey === group.issue.key ? 'true' : undefined"
              @click="openIssue(group.issue)"
            >
              {{ group.issue.key }}
            </button>
            <span class="contexts__group-summary">{{ group.issue.summary || 'Fora do espelho local' }}</span>
            <span v-if="group.issue.status" class="contexts__group-status">{{ group.issue.status }}</span>
          </h2>
          <ContextCard
            v-for="c in group.items"
            :key="c.id"
            :context="c"
            :highlight="route.query.q ?? ''"
            hide-issue
            @edit="contexts.openEditor"
            @delete="(ctx) => contexts.remove(ctx.id)"
            @reopen="(ctx) => contexts.reopen(ctx.id)"
            @resolve="resolve"
            @open-issue="openIssue"
          />
        </section>
      </template>
    </section>

    <IssueDrawer v-if="issueKey" :issue-key="issueKey" @close="setQuery({ tarefa: null })" @open="(k) => setQuery({ tarefa: k })" />
  </div>
</template>

<style scoped>
.contexts-page {
  height: 100%;
  display: flex;
  gap: var(--space-4);
}

.contexts {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.contexts__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
}

.contexts__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.contexts__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.contexts__search {
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

.contexts__search:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.contexts__search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  font: inherit;
  font-size: var(--text-sm);
}

.contexts__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.contexts__filter {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.contexts__filter small {
  color: var(--color-text-muted);
}

.contexts__filter--on {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-weight: 600;
}

.contexts__count {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.contexts__group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.contexts__group + .contexts__group {
  margin-top: var(--space-2);
}

.contexts__group-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 500;
}

.contexts__group-key {
  flex-shrink: 0;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 700;
  color: var(--color-primary);
}

.contexts__group-key[aria-current] {
  text-decoration: underline;
}

.contexts__group-key--external {
  color: var(--color-text-secondary);
}

.contexts__group-summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contexts__group-status {
  flex-shrink: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.contexts__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-6);
  text-align: center;
  color: var(--color-text-secondary);
}

.contexts__empty p {
  margin: 0;
}

.contexts__error {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
}
</style>
