import { defineStore } from 'pinia'
import { api } from '@/services/api'

const POLL_IDLE_MS = 30_000
const POLL_RUNNING_MS = 3_000

export const useSyncStore = defineStore('sync', {
  state: () => ({
    status: null,
    statusError: null,
    scope: null,
    scopeLoading: false,
    scopeSaving: false,
    scopeFeedback: null,
    sprints: [],
    triggering: false,
    triggerError: null,
    _timer: null,
  }),
  getters: {
    running: (state) => Boolean(state.status?.running),
    lastRun: (state) => state.status?.last_run ?? null,
    hasRun: (state) => Boolean(state.status?.last_run),
    selectedRepos: (state) => state.scope?.bitbucket?.repo_slugs ?? [],
  },
  actions: {
    async loadStatus() {
      try {
        const wasRunning = this.running
        this.status = await api.get('/sync/status')
        this.statusError = null
        // Execução acabou: atualiza a contagem por sprint.
        if (wasRunning && !this.running) await this.loadSprints()
      } catch (error) {
        this.statusError = error.message
      }
    },

    startPolling() {
      if (this._timer) return
      const tick = async () => {
        await this.loadStatus()
        this._timer = setTimeout(tick, this.running ? POLL_RUNNING_MS : POLL_IDLE_MS)
      }
      tick()
    },

    stopPolling() {
      clearTimeout(this._timer)
      this._timer = null
    },

    async loadScope() {
      this.scopeLoading = true
      try {
        this.scope = await api.get('/sync/scope')
      } finally {
        this.scopeLoading = false
      }
    },

    async saveScope(scope) {
      this.scopeSaving = true
      this.scopeFeedback = null
      try {
        this.scope = await api.put('/sync/scope', scope)
        this.scopeFeedback = { type: 'success', text: 'Escopo salvo. Vale a partir da próxima sincronização.' }
        return true
      } catch (error) {
        this.scopeFeedback = { type: 'error', text: error.message }
        return false
      } finally {
        this.scopeSaving = false
      }
    },

    async loadSprints() {
      try {
        this.sprints = await api.get('/sync/sprints')
      } catch {
        this.sprints = []
      }
    },

    async trigger() {
      this.triggering = true
      this.triggerError = null
      try {
        await api.post('/sync')
      } catch (error) {
        this.triggerError = error.message
      } finally {
        this.triggering = false
      }
      // Reinicia o polling já no ritmo rápido.
      this.stopPolling()
      this.startPolling()
    },
  },
})
