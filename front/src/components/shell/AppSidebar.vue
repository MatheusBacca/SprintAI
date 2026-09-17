<script setup>
import { computed } from 'vue'
import {
  BookOpenText,
  CalendarDays,
  House,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sparkles,
  StickyNote,
  Sun,
  Workflow,
} from 'lucide-vue-next'
import { navItems } from '@/router/routes'
import { useUiStore } from '@/stores/ui'

// Import explícito: `import *` levaria o pacote inteiro de ícones para o bundle.
const icons = { BookOpenText, CalendarDays, House, Settings, StickyNote, Workflow }

const ui = useUiStore()

// Sem a dica do Shift, quem clica uma vez fica preso na escolha manual para sempre.
const themeLabel = computed(() => {
  const acao = ui.isDark ? 'Mudar para o tema claro' : 'Mudar para o tema escuro'
  return ui.themeChoice ? `${acao} (Shift+clique volta a seguir o Windows)` : acao
})

function onThemeClick(event) {
  if (event.shiftKey) ui.followSystem()
  else ui.toggleTheme()
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': ui.sidebarCollapsed }">
    <RouterLink to="/" class="sidebar__brand" :title="ui.sidebarCollapsed ? 'SprintAI' : undefined">
      <span class="sidebar__logo"><Sparkles :size="18" /></span>
      <span class="sidebar__name">SprintAI</span>
    </RouterLink>

    <nav class="sidebar__nav" aria-label="Navegação principal">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.path"
        class="sidebar__item"
        active-class=""
        exact-active-class="sidebar__item--active"
        :title="ui.sidebarCollapsed ? item.meta.title : undefined"
        :aria-label="item.meta.title"
      >
        <component :is="icons[item.meta.icon]" :size="18" class="sidebar__item-icon" />
        <span class="sidebar__label">{{ item.meta.title }}</span>
      </RouterLink>
    </nav>

    <div class="sidebar__footer">
      <p class="sidebar__footer-title">Seu histórico, local</p>
      <p class="sidebar__footer-text">
        Tarefas, contextos e lembretes ficam nesta máquina. Chaves no Cofre do Windows.
      </p>
    </div>

    <div class="sidebar__actions">
      <button
        type="button"
        class="sidebar__toggle"
        :aria-expanded="!ui.sidebarCollapsed"
        :title="ui.sidebarCollapsed ? 'Expandir menu' : 'Recolher menu'"
        @click="ui.toggleSidebar()"
      >
        <PanelLeftOpen v-if="ui.sidebarCollapsed" :size="18" />
        <PanelLeftClose v-else :size="18" />
        <span class="sidebar__label">Recolher menu</span>
      </button>

      <button
        type="button"
        class="sidebar__theme"
        :title="themeLabel"
        :aria-label="themeLabel"
        :aria-pressed="ui.isDark"
        @click="onThemeClick"
      >
        <Sun v-if="ui.isDark" :size="18" />
        <Moon v-else :size="18" />
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-sidebar);
  color: var(--color-sidebar-text);
  padding: var(--space-5) var(--space-3) var(--space-3);
  overflow: hidden;
  transition: width var(--duration-panel) ease;
}

.sidebar--collapsed {
  width: var(--sidebar-width-collapsed);
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-2) var(--space-6);
  color: var(--color-sidebar-text-strong);
  white-space: nowrap;
}

.sidebar__logo {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-deep));
}

.sidebar__name {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 10px var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  white-space: nowrap;
  transition: background var(--duration-fast);
}

.sidebar__item-icon {
  flex-shrink: 0;
}

.sidebar__item:hover {
  background: var(--color-sidebar-hover);
  color: var(--color-sidebar-text-strong);
}

.sidebar__item--active {
  background: var(--color-sidebar-active);
  color: var(--color-sidebar-text-strong);
  font-weight: 600;
}

.sidebar__footer {
  margin-top: auto;
  padding: var(--space-4);
  border: 1px solid var(--color-sidebar-border);
  border-radius: var(--radius-lg);
}

.sidebar__footer-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-sidebar-text-strong);
}

.sidebar__footer-text {
  margin: 0;
  font-size: var(--text-xs);
  line-height: 17px;
}

.sidebar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-3);
}

.sidebar__toggle,
.sidebar__theme {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 10px var(--space-3);
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-sidebar-text);
  font-size: var(--text-sm);
  white-space: nowrap;
  transition: background var(--duration-fast);
}

.sidebar__toggle {
  flex: 1;
  min-width: 0;
}

.sidebar__theme {
  flex-shrink: 0;
}

.sidebar__toggle:hover,
.sidebar__theme:hover {
  background: var(--color-sidebar-hover);
  color: var(--color-sidebar-text-strong);
}

/* Recolhida: só ícones centralizados */
.sidebar--collapsed .sidebar__label,
.sidebar--collapsed .sidebar__name,
.sidebar--collapsed .sidebar__footer {
  display: none;
}

.sidebar--collapsed .sidebar__brand {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}

.sidebar--collapsed .sidebar__item,
.sidebar--collapsed .sidebar__toggle,
.sidebar--collapsed .sidebar__theme {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}

/* Recolhida não cabem dois ícones lado a lado: viram uma coluna no rodapé. */
.sidebar--collapsed .sidebar__actions {
  flex-direction: column;
  align-items: stretch;
  margin-top: auto;
}
</style>
