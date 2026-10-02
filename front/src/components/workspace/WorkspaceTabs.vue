<script setup>
import { FolderGit2, Plus, X } from 'lucide-vue-next'

/**
 * As abas dos workspaces abertos, no topo da tela Workspace. Ficam aqui, e não no topo do
 * app: lá já moram os lembretes fixados, e uma fileira de abas em toda tela comeria o
 * espaço da busca. Fechar a aba não apaga o workspace.
 */
defineProps({
  tabs: { type: Array, required: true },
  currentId: { type: Number, default: null },
})
const emit = defineEmits(['select', 'close', 'new'])
</script>

<template>
  <nav class="tabs" aria-label="Workspaces abertos">
    <ul class="tabs__list" role="tablist">
      <li
        v-for="tab in tabs"
        :key="tab.id"
        class="tabs__item"
        :class="{ 'tabs__item--active': tab.id === currentId }"
        :data-id="tab.id"
      >
        <button
          type="button"
          role="tab"
          class="tabs__open"
          :aria-selected="tab.id === currentId"
          :title="tab.root_issue_key ? `${tab.root_issue_key} — ${tab.title}` : tab.title"
          @click="emit('select', tab.id)"
        >
          <FolderGit2 :size="13" />
          <span v-if="tab.root_issue_key" class="tabs__key">{{ tab.root_issue_key }}</span>
          <span class="tabs__title">{{ tab.title }}</span>
        </button>
        <button type="button" class="tabs__close" title="Fechar aba" aria-label="Fechar aba" @click="emit('close', tab.id)">
          <X :size="12" />
        </button>
      </li>
    </ul>
    <button type="button" class="tabs__new" title="Novo workspace" aria-label="Novo workspace" @click="emit('new')">
      <Plus :size="14" />
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.tabs__list {
  display: flex;
  gap: var(--space-2);
  min-width: 0;
  margin: 0;
  padding: 0;
  overflow-x: auto;
  list-style: none;
  scrollbar-width: thin;
}

.tabs__item {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.tabs__item--active {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}

.tabs__open {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 280px;
  padding: 5px 4px 5px 10px;
  border: 0;
  background: none;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.tabs__item--active .tabs__open {
  color: var(--color-text);
}

.tabs__key {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--color-primary);
}

.tabs__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tabs__close,
.tabs__new {
  display: grid;
  place-items: center;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.tabs__close {
  width: 22px;
  height: 24px;
}

.tabs__new {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: 1px dashed var(--color-border-strong);
}

.tabs__close:hover,
.tabs__new:hover {
  color: var(--color-primary);
}
</style>
