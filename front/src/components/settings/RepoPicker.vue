<script setup>
import { computed, onMounted, ref } from 'vue'
import { Search } from 'lucide-vue-next'
import { api } from '@/services/api'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  modelValue: { type: Array, required: true },
})
const emit = defineEmits(['update:modelValue'])

const repos = ref([])
const loading = ref(false)
const error = ref(null)
const query = ref('')

const selected = computed(() => new Set(props.modelValue))

onMounted(load)

async function load() {
  loading.value = true
  error.value = null
  try {
    repos.value = await api.get('/bitbucket/repositories?limit=1000')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const groups = computed(() => {
  const term = query.value.trim().toLowerCase()
  const byProject = new Map()
  for (const repo of repos.value) {
    const project = repo.project_name || 'Sem projeto'
    if (term && !`${repo.slug} ${project}`.toLowerCase().includes(term)) continue
    if (!byProject.has(project)) byProject.set(project, [])
    byProject.get(project).push(repo)
  }
  return [...byProject.entries()]
    .sort(([a], [b]) => a.localeCompare(b, 'pt-BR'))
    .map(([project, items]) => ({
      project,
      repos: items.sort((a, b) => a.slug.localeCompare(b.slug)),
      selectedCount: items.filter((r) => selected.value.has(r.slug)).length,
    }))
})

// Escolhidos que não existem mais no workspace (renomeados/removidos).
const missing = computed(() => {
  if (!repos.value.length) return []
  const known = new Set(repos.value.map((r) => r.slug))
  return props.modelValue.filter((slug) => !known.has(slug))
})

function toggle(slug) {
  const next = new Set(selected.value)
  next.has(slug) ? next.delete(slug) : next.add(slug)
  emit('update:modelValue', [...next].sort())
}

function toggleProject(group) {
  const next = new Set(selected.value)
  const allSelected = group.selectedCount === group.repos.length
  for (const repo of group.repos) allSelected ? next.delete(repo.slug) : next.add(repo.slug)
  emit('update:modelValue', [...next].sort())
}
</script>

<template>
  <div class="picker">
    <div class="picker__toolbar">
      <label class="picker__search">
        <Search :size="14" />
        <input v-model="query" type="search" placeholder="Filtrar por repositório ou projeto">
      </label>
      <span class="picker__count">{{ modelValue.length }} escolhido(s)</span>
    </div>

    <p v-if="loading" class="muted">Carregando repositórios do Bitbucket…</p>
    <p v-else-if="error" class="picker__error" role="alert">
      {{ error }} <button type="button" class="btn btn--secondary" @click="load">Tentar de novo</button>
    </p>

    <p v-if="missing.length" class="picker__error">
      Não encontrados no workspace: {{ missing.join(', ') }}
    </p>

    <div v-if="!loading && !error" class="picker__groups">
      <section v-for="group in groups" :key="group.project" class="picker__group">
        <label class="picker__project">
          <input
            type="checkbox"
            :checked="group.selectedCount === group.repos.length"
            :indeterminate.prop="group.selectedCount > 0 && group.selectedCount < group.repos.length"
            @change="toggleProject(group)"
          >
          <strong>{{ group.project }}</strong>
          <span class="muted">{{ group.selectedCount }}/{{ group.repos.length }}</span>
        </label>
        <ul class="picker__repos">
          <li v-for="repo in group.repos" :key="repo.slug">
            <label class="picker__repo">
              <input type="checkbox" :checked="selected.has(repo.slug)" @change="toggle(repo.slug)">
              <span class="picker__slug">{{ repo.slug }}</span>
              <span class="muted">{{ formatRelative(repo.updated_on) }}</span>
            </label>
          </li>
        </ul>
      </section>
      <p v-if="!groups.length" class="muted">Nenhum repositório encontrado.</p>
    </div>
  </div>
</template>

<style scoped>
.picker {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.picker__toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.picker__search {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
}

.picker__search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  font: inherit;
  font-size: var(--text-sm);
}

.picker__count {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
  white-space: nowrap;
}

.picker__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.picker__groups {
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.picker__group + .picker__group {
  border-top: 1px solid var(--color-border);
}

.picker__project {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-muted);
  font-size: var(--text-sm);
  cursor: pointer;
}

.picker__repos {
  list-style: none;
  margin: 0;
  padding: var(--space-1) 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

.picker__repo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px var(--space-3) 4px 28px;
  font-size: var(--text-sm);
  cursor: pointer;
}

.picker__repo:hover {
  background: var(--color-surface-hover);
}

.picker__slug {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker__repo .muted {
  font-size: var(--text-xs);
}
</style>
