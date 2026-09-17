import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { DEFAULT_BINDINGS } from '@/utils/shortcuts'

export const useShortcutsStore = defineStore('shortcuts', {
  state: () => ({
    bindings: { ...DEFAULT_BINDINGS },
    defaults: { ...DEFAULT_BINDINGS },
    loaded: false,
    saving: false,
    error: null,
    // Configurações › Atalhos gravando uma tecla: os atalhos globais ficam suspensos.
    recording: false,
  }),
  getters: {
    actionFor: (state) => (combo) =>
      Object.keys(state.bindings).find((action) => combo && state.bindings[action] === combo) ?? null,
  },
  actions: {
    async load() {
      try {
        const result = await api.get('/preferences/shortcuts')
        this.bindings = { ...DEFAULT_BINDINGS, ...result?.bindings }
        this.defaults = { ...DEFAULT_BINDINGS, ...result?.defaults }
        this.error = null
      } catch (error) {
        // Sem API os atalhos padrão continuam valendo.
        this.error = error.message
      } finally {
        this.loaded = true
      }
    },

    async save(bindings) {
      this.saving = true
      try {
        const result = await api.put('/preferences/shortcuts', { bindings })
        this.bindings = { ...DEFAULT_BINDINGS, ...result?.bindings }
        this.error = null
        return true
      } catch (error) {
        this.error = error.message
        return false
      } finally {
        this.saving = false
      }
    },
  },
})
