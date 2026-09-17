import { defineStore } from 'pinia'

/**
 * O que está na tela agora. Preenchido pelas views; lido pela modal de lembretes
 * (F4.1, para pré-filtrar pela tarefa em foco) e, no M4, pela IA.
 */
export const useScreenContextStore = defineStore('screenContext', {
  state: () => ({
    view: null,
    sprintId: null,
    focusedIssueKey: null,
    visibleIssueKeys: [],
    filters: {},
  }),
  actions: {
    enter(view, patch = {}) {
      this.$patch({ view, sprintId: null, focusedIssueKey: null, visibleIssueKeys: [], filters: {}, ...patch })
    },
    focusIssue(key) {
      this.focusedIssueKey = key
    },
  },
})
