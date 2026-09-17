import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'

const PAGE = 25

export const useActivityStore = defineStore('activity', {
  state: () => ({
    events: [],
    cursor: null,
    loading: false,
    loadingMore: false,
    error: null,
    source: null, // null | 'jira' | 'bitbucket'
    onlyOthers: false,
    _requestId: 0,
  }),
  getters: {
    hasMore: (state) => Boolean(state.cursor),
    /** Agrupado por dia (a data já vem no fuso do navegador pelo `Date`). */
    days: (state) => {
      const groups = new Map()
      for (const event of state.events) {
        const day = new Date(event.occurred_at).toDateString()
        if (!groups.has(day)) groups.set(day, { day, at: event.occurred_at, events: [] })
        groups.get(day).events.push(event)
      }
      return [...groups.values()]
    },
  },
  actions: {
    _query(cursor) {
      return toQuery({
        cursor,
        limit: PAGE,
        source: this.source,
        only_others: this.onlyOthers ? 'true' : null,
      })
    },

    async load() {
      const requestId = ++this._requestId
      this.loading = true
      try {
        const data = await api.get(`/activity${this._query(null)}`)
        if (requestId !== this._requestId) return
        if (!Array.isArray(data?.events)) throw new Error('Resposta inesperada da API de atividade.')
        this.events = data.events
        this.cursor = data.next_cursor
        this.error = null
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    async loadMore() {
      if (!this.cursor || this.loadingMore) return
      const requestId = this._requestId
      this.loadingMore = true
      try {
        const data = await api.get(`/activity${this._query(this.cursor)}`)
        // Um filtro trocado no meio do caminho invalida esta página.
        if (requestId !== this._requestId) return
        if (!Array.isArray(data?.events)) throw new Error('Resposta inesperada da API de atividade.')
        const known = new Set(this.events.map((e) => e.id))
        this.events = [...this.events, ...data.events.filter((e) => !known.has(e.id))]
        this.cursor = data.next_cursor
      } catch (error) {
        this.error = error.message
      } finally {
        this.loadingMore = false
      }
    },

    async setFilters({ source, onlyOthers }) {
      if (source !== undefined) this.source = source
      if (onlyOthers !== undefined) this.onlyOthers = onlyOthers
      await this.load()
    },
  },
})
