import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * Configurações › Concluir: a receita de cada repositório — para que status do Jira a tarefa
 * vai e se o PR aberto é mergeado (estratégia, fechar a branch). Repo sem receita não tem o
 * botão "Concluir" nos cards.
 */
export const useConcludeSettingsStore = defineStore('concludeSettings', {
  state: () => ({
    repos: {},
    knownRepos: [],
    statuses: [],
    loaded: false,
    saving: false,
    error: null,
    /** `{ type: 'success' | 'error', text }` do último salvar. */
    feedback: null,
  }),
  actions: {
    _apply(data) {
      this.repos = data.repos
      this.knownRepos = data.known_repos
      this.statuses = data.statuses
      this.loaded = true
    },

    async load() {
      this.error = null
      try {
        this._apply(await api.get('/preferences/conclude'))
      } catch (error) {
        this.error = error.message
      }
    },

    async save(repos) {
      this.saving = true
      this.feedback = null
      try {
        this._apply(await api.put('/preferences/conclude', { repos }))
        this.feedback = { type: 'success', text: 'Receitas salvas. Os cards mostram o Concluir na próxima recarga.' }
        return true
      } catch (error) {
        this.feedback = { type: 'error', text: error.message }
        return false
      } finally {
        this.saving = false
      }
    },
  },
})
