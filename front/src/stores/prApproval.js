import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * Regra de aprovação do PR (Configurações › Fluxo de trabalho › Pull requests): quanto dos revisores precisa
 * aprovar para o badge dizer "Aprovada". A conta é do back — as telas recebem o status
 * pronto; aqui só se lê e grava a regra.
 */
export const usePrApprovalStore = defineStore('prApproval', {
  state: () => ({
    minPercent: null,
    // Piso em número de aprovações, somado à porcentagem. 0: sem piso.
    minApprovals: 0,
    loading: false,
    saving: false,
    error: null,
    feedback: null,
  }),
  actions: {
    async load() {
      this.loading = true
      try {
        const data = await api.get('/preferences/pr-approval')
        this.minPercent = data.min_percent
        this.minApprovals = data.min_approvals ?? 0
        this.error = null
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    },

    async save(minPercent, minApprovals = this.minApprovals) {
      this.saving = true
      this.feedback = null
      try {
        const data = await api.put('/preferences/pr-approval', { min_percent: minPercent, min_approvals: minApprovals })
        this.minPercent = data.min_percent
        this.minApprovals = data.min_approvals ?? 0
        this.feedback = { type: 'success', text: 'Regra salva. Os cards já contam as aprovações por ela.' }
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
