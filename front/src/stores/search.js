import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'

export const SEARCH_TYPES = [
  { id: 'issue', label: 'Tarefas' },
  { id: 'comment', label: 'Comentários' },
  { id: 'pull_request', label: 'PRs' },
  { id: 'context', label: 'Contextos' },
  { id: 'note', label: 'Lembretes' },
]

export const SEARCH_PERIODS = [
  { id: 'any', label: 'Qualquer data' },
  { id: '7d', label: 'Últimos 7 dias' },
  { id: '30d', label: 'Últimos 30 dias' },
  { id: '90d', label: 'Últimos 90 dias' },
  { id: '365d', label: 'Último ano' },
]

const PER_TYPE = 5
const PAGE = 20
export const MIN_QUERY = 2

export const useSearchStore = defineStore('search', {
  state: () => ({
    open: false,
    query: '',
    type: 'all',
    period: 'any',
    loading: false,
    loadingMore: false,
    error: null,
    result: null,
    // Totais por tipo da última busca em "Tudo": os filtros mostram a contagem mesmo filtrados.
    totals: {},
    _requestId: 0,
  }),
  getters: {
    hits: (state) => state.result?.groups.flatMap((g) => g.items) ?? [],
  },
  actions: {
    openSearch(query = null) {
      if (query) this.query = query
      this.open = true
    },

    close() {
      this.open = false
    },

    async run() {
      const requestId = ++this._requestId
      const q = this.query.trim()
      if (q.length < MIN_QUERY) {
        this.result = null
        this.totals = {}
        this.loading = false
        this.error = null
        return
      }
      this.loading = true
      this.error = null
      try {
        const single = this.type !== 'all'
        const result = await api.get(
          `/search${toQuery({ q, type: single ? [this.type] : [], period: this.period, limit: single ? PAGE : PER_TYPE })}`,
        )
        if (requestId !== this._requestId) return
        this.result = result
        if (!single) this.totals = Object.fromEntries(result.groups.map((g) => [g.type, g.total]))
        else this.totals = { ...this.totals, [this.type]: result.total }
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    async loadMore() {
      const group = this.result?.groups[0]
      if (this.type === 'all' || !group || group.items.length >= group.total) return
      const requestId = this._requestId
      this.loadingMore = true
      try {
        const page = await api.get(
          `/search${toQuery({ q: this.query.trim(), type: [this.type], period: this.period, limit: PAGE, offset: group.items.length })}`,
        )
        if (requestId !== this._requestId) return
        group.items.push(...(page.groups[0]?.items ?? []))
      } catch (error) {
        this.error = error.message
      } finally {
        this.loadingMore = false
      }
    },

    setType(type) {
      this.type = type
      return this.run()
    },

    setPeriod(period) {
      this.period = period
      return this.run()
    },
  },
})
