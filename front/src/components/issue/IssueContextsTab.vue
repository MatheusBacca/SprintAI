<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import ContextCard from '@/components/contexts/ContextCard.vue'
import { CONTEXT_KINDS, CONTEXT_KIND_KEYS } from '@/constants/contextKinds'
import { useContextsStore } from '@/stores/contexts'
import { safeUrl } from '@/utils/safeUrl'

const props = defineProps({
  issueKey: { type: String, required: true },
})
const emit = defineEmits(['open', 'count'])

const contexts = useContextsStore()
const data = ref({ own: [], linked: [], nearby_open: [] })
const loading = ref(false)
const error = ref(null)
let requestId = 0

async function load() {
  const id = ++requestId
  loading.value = true
  error.value = null
  try {
    const result = await contexts.forIssue(props.issueKey)
    if (id !== requestId) return
    data.value = result
    emit('count', result.own.length + result.linked.length)
  } catch (e) {
    if (id === requestId) error.value = e.message
  } finally {
    if (id === requestId) loading.value = false
  }
}

onMounted(load)
watch(() => [props.issueKey, contexts.revision], load)

const empty = computed(() => !data.value.own.length && !data.value.linked.length && !data.value.nearby_open.length)

function create(kind) {
  contexts.openEditor(null, { kind, issue_key: props.issueKey })
}

function openIssue(issue) {
  if (issue.key === props.issueKey) return
  if (issue.in_mirror) emit('open', issue.key)
  else if (safeUrl(issue.url)) window.open(safeUrl(issue.url), '_blank', 'noopener')
}

const handlers = {
  onEdit: (c) => contexts.openEditor(c),
  onDelete: (c) => contexts.remove(c.id),
  onReopen: (c) => contexts.reopen(c.id),
  // No painel desta tarefa, "resolver" já sugere esta tarefa como onde foi resolvido.
  onResolve: (c) => contexts.openResolver(c, props.issueKey),
}
</script>

<template>
  <div class="issue-ctx">
    <div class="issue-ctx__new" role="group" aria-label="Novo contexto">
      <span>Registrar:</span>
      <button
        v-for="key in CONTEXT_KIND_KEYS"
        :key="key"
        type="button"
        class="issue-ctx__kind"
        :title="CONTEXT_KINDS[key].hint"
        :style="{ '--k-color': CONTEXT_KINDS[key].color, '--k-bg': CONTEXT_KINDS[key].bg }"
        @click="create(key)"
      >
        <component :is="CONTEXT_KINDS[key].icon" :size="13" /> {{ CONTEXT_KINDS[key].label }}
      </button>
    </div>

    <p v-if="error" class="issue-ctx__empty" role="alert">{{ error }}</p>
    <p v-else-if="!loading && empty" class="issue-ctx__empty">
      Nenhum contexto ainda. Registre achados, correções, decisões e o que ficou em aberto — eles voltam quando uma
      tarefa relacionada aparecer.
    </p>

    <section v-if="data.own.length" class="issue-ctx__section">
      <h3>Desta tarefa <small>{{ data.own.length }}</small></h3>
      <ContextCard
        v-for="c in data.own"
        :key="c.id"
        :context="c"
        hide-issue
        @edit="handlers.onEdit"
        @delete="handlers.onDelete"
        @reopen="handlers.onReopen"
        @resolve="handlers.onResolve"
        @open-issue="openIssue"
      />
    </section>

    <section v-if="data.linked.length" class="issue-ctx__section">
      <h3>De outras tarefas que citam esta <small>{{ data.linked.length }}</small></h3>
      <ContextCard
        v-for="c in data.linked"
        :key="c.id"
        :context="c"
        @edit="handlers.onEdit"
        @delete="handlers.onDelete"
        @reopen="handlers.onReopen"
        @resolve="handlers.onResolve"
        @open-issue="openIssue"
      />
    </section>

    <section v-if="data.nearby_open.length" class="issue-ctx__section">
      <h3>Em aberto em tarefas próximas <small>{{ data.nearby_open.length }}</small></h3>
      <p class="issue-ctx__hint">Mesmo pai, pai/filhas ou vínculo no Jira. Algum deles se resolve aqui?</p>
      <ContextCard
        v-for="c in data.nearby_open"
        :key="c.id"
        :context="c"
        resolve-label="Resolver aqui"
        @edit="handlers.onEdit"
        @delete="handlers.onDelete"
        @reopen="handlers.onReopen"
        @resolve="handlers.onResolve"
        @open-issue="openIssue"
      />
    </section>
  </div>
</template>

<style scoped>
.issue-ctx {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.issue-ctx__new {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.issue-ctx__kind {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: var(--color-surface);
  font-size: 11px;
  font-weight: 600;
  color: var(--k-color);
}

.issue-ctx__kind:hover {
  border-color: var(--k-color);
  background: var(--k-bg);
}

.issue-ctx__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.issue-ctx__section h3 {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.issue-ctx__section h3 small {
  margin-left: 4px;
  font-size: inherit;
  color: var(--color-text-secondary);
}

.issue-ctx__hint,
.issue-ctx__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.issue-ctx__hint {
  margin-top: -4px;
  font-size: var(--text-xs);
}
</style>
