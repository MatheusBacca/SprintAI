import { defineStore } from 'pinia'

const SIDEBAR_KEY = 'sprintai.sidebarCollapsed'
const THEME_KEY = 'sprintai.theme'

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

/** Preferência explícita do dev: 'light', 'dark' ou null (= segue o sistema). */
function readThemeChoice() {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    return saved === 'light' || saved === 'dark' ? saved : null
  } catch {
    return null
  }
}

function systemPrefersDark() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false
}

/**
 * Escreve o tema no <html>. O mesmo atributo é aplicado pelo bootstrap inline
 * do index.html antes do Vue montar — aqui só mantemos os dois em sincronia.
 */
function applyTheme(theme) {
  if (typeof document === 'undefined') return
  if (theme === 'dark') document.documentElement.dataset.theme = 'dark'
  else delete document.documentElement.dataset.theme
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    sidebarCollapsed: readCollapsed(),
    themeChoice: readThemeChoice(),
    systemDark: systemPrefersDark(),
    // Aba pedida para o painel da tarefa que vai abrir (ex.: busca → comentário → Histórico).
    issueTabRequest: null,
  }),
  getters: {
    /** Tema efetivo na tela: a escolha do dev quando existe, senão o do sistema. */
    theme: (state) => state.themeChoice ?? (state.systemDark ? 'dark' : 'light'),
    isDark() {
      return this.theme === 'dark'
    },
  },
  actions: {
    requestIssueTab(key, tab) {
      this.issueTabRequest = tab ? { key, tab } : null
    },

    consumeIssueTab(key) {
      const request = this.issueTabRequest
      if (!request || request.key !== key) return null
      this.issueTabRequest = null
      return request.tab
    },

    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      try {
        localStorage.setItem(SIDEBAR_KEY, this.sidebarCollapsed ? '1' : '0')
      } catch {
        // preferência só da sessão
      }
    },

    setTheme(theme) {
      this.themeChoice = theme === 'dark' ? 'dark' : 'light'
      applyTheme(this.theme)
      try {
        localStorage.setItem(THEME_KEY, this.themeChoice)
      } catch {
        // preferência só da sessão
      }
    },

    toggleTheme() {
      this.setTheme(this.isDark ? 'light' : 'dark')
    },

    /**
     * Passa a seguir o Windows de novo. Enquanto o dev não clicar no botão, é
     * este o estado — por isso `themeChoice` nasce nulo e não 'light'.
     */
    followSystem() {
      this.themeChoice = null
      this.systemDark = systemPrefersDark()
      applyTheme(this.theme)
      try {
        localStorage.removeItem(THEME_KEY)
      } catch {
        // preferência só da sessão
      }
    },

    /** Liga o app à preferência do SO; devolve o desligamento para o caller. */
    watchSystemTheme() {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return () => {}
      const query = window.matchMedia('(prefers-color-scheme: dark)')
      const onChange = (event) => {
        this.systemDark = event.matches
        if (!this.themeChoice) applyTheme(this.theme)
      }
      query.addEventListener('change', onChange)
      applyTheme(this.theme)
      return () => query.removeEventListener('change', onChange)
    },
  },
})
