import { defineStore } from 'pinia'
import { api } from '@/services/api'

/** Etapas do progresso (B9) — lidas pela Home e editadas em Configurações › Progresso. */
export const useProgressStore = defineStore('progress', {
  state: () => ({
    stages: [],
    statuses: [],
    loading: false,
    saving: false,
    error: null,
    feedback: null,
  }),
  getters: {
    stageById: (state) => Object.fromEntries(state.stages.map((s) => [s.id, s])),
    colorOf: (state) => (stageId) => state.stages.find((s) => s.id === stageId)?.color ?? null,
  },
  actions: {
    async load() {
      this.loading = true
      try {
        const data = await api.get('/progress/stages')
        this.stages = data.stages
        this.statuses = data.statuses
        this.error = null
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    },

    async save({ stages, statuses }) {
      this.saving = true
      this.feedback = null
      try {
        const data = await api.put('/progress/stages', { stages, statuses })
        this.stages = data.stages
        this.statuses = data.statuses
        this.feedback = { type: 'success', text: 'Etapas salvas. O progresso já usa os novos pesos.' }
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
