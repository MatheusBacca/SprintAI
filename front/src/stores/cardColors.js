import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * Cores dos cards (Configurações › Cores dos cards): o fundo esfumaçado dos pais pelo tipo
 * e das tarefas pelo `[repo]` do título. Quem decide a cor de cada card é o back — a
 * árvore da sprint já chega com o `tint` —; aqui só se lê e grava a configuração.
 */
export const useCardColorsStore = defineStore('cardColors', {
  state: () => ({
    types: [],
    repos: [],
    suggestions: [],
    loaded: false,
    loading: false,
    saving: false,
    error: null,
    feedback: null,
  }),
  actions: {
    apply(data) {
      this.types = data.types
      this.repos = data.repos
      this.suggestions = data.suggestions
      this.loaded = true
    },

    async load() {
      this.loading = true
      try {
        this.apply(await api.get('/preferences/card-colors'))
        this.error = null
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    },

    /** `types` e `repos` são mapas id/slug → cor (`null` tira a cor); `aliases`, slug → apelidos. */
    async save({ types, repos, aliases }) {
      this.saving = true
      this.feedback = null
      try {
        this.apply(await api.put('/preferences/card-colors', { types, repos, aliases }))
        this.feedback = { type: 'success', text: 'Cores salvas. O canvas da sprint já abre com elas.' }
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
