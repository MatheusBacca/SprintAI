import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'
import { browserTimezone } from '@/stores/week'

export const useHomeStore = defineStore('home', {
  state: () => ({
    data: null,
    timeline: null,
    loading: false,
    timelineLoading: false,
    error: null,
    timelineError: null,
    includeNext: true,
    _requestId: 0,
  }),
  getters: {
    sprints: (state) => state.data?.sprints ?? [],
    overdueSprint: (state) => (state.data?.sprints ?? []).find((s) => s.overdue_active) ?? null,
    /** Tarefas visíveis na tela (alimenta o `screenContext`). */
    issueKeys: (state) => {
      const p = state.data?.pending
      const fromPending = p ? [...p.overdue, ...p.due, ...p.slicing, ...p.without_sprint] : []
      const fromTimeline = (state.timeline?.groups ?? []).flatMap((g) => g.issues)
      return [...new Set([...fromPending, ...fromTimeline].map((i) => i.key))]
    },
  },
  actions: {
    async load() {
      const requestId = ++this._requestId
      this.loading = true
      try {
        const data = await api.get(`/home${toQuery({ tz: browserTimezone() })}`)
        if (requestId !== this._requestId) return
        if (!Array.isArray(data?.sprints)) throw new Error('Resposta inesperada da API da Home.')
        this.data = data
        this.error = null
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    async loadTimeline() {
      this.timelineLoading = true
      try {
        const query = toQuery({ tz: browserTimezone(), include_next: this.includeNext })
        this.timeline = await api.get(`/home/timeline${query}`)
        this.timelineError = null
      } catch (error) {
        this.timelineError = error.message
      } finally {
        this.timelineLoading = false
      }
    },

    async loadAll() {
      await Promise.all([this.load(), this.loadTimeline()])
    },

    async setIncludeNext(value) {
      this.includeNext = value
      await this.loadTimeline()
    },
  },
})
