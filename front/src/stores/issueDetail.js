import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { useRefreshStore } from '@/stores/refresh'

/** Chave do cache da linha do tempo — um PR é (repo, número), não só o número. */
export function prKey(repoSlug, prId) {
  return `${repoSlug}#${prId}`
}

/**
 * Serve do cache só se ele foi buscado depois do último sync. Sem isto, reabrir o
 * painel de uma tarefa já vista mostraria o estado de antes da sincronização — e
 * `invalidate()` a cada sync faria o painel aberto piscar "Carregando…".
 */
function isFresh(entry, revision) {
  return Boolean(entry) && entry.revision === revision
}

export const useIssueDetailStore = defineStore('issueDetail', {
  state: () => ({
    // cache por chave: { data, loading, error, revision }
    issues: {},
    changelogs: {},
    // Histórico do PR, por `repo#id`.
    prTimelines: {},
  }),
  actions: {
    async load(key, { force = false } = {}) {
      const revision = useRefreshStore().revision
      const entry = this.issues[key]
      if (!force && isFresh(entry, revision) && (entry.data || entry.loading)) return
      // Mantém o que já está na tela enquanto busca: recarregar não pode piscar.
      this.issues[key] = { data: entry?.data ?? null, loading: true, error: null, revision }
      try {
        const data = await api.get(`/issues/${encodeURIComponent(key)}`)
        this.issues[key] = { data, loading: false, error: null, revision }
      } catch (error) {
        this.issues[key] = { data: entry?.data ?? null, loading: false, error: error.message, revision }
      }
    },

    async loadChangelog(key, { force = false } = {}) {
      const revision = useRefreshStore().revision
      const entry = this.changelogs[key]
      if (!force && isFresh(entry, revision) && (entry.data || entry.loading)) return
      this.changelogs[key] = { data: entry?.data ?? null, loading: true, error: null, revision }
      try {
        const data = await api.get(`/issues/${encodeURIComponent(key)}/changelog`)
        this.changelogs[key] = { data, loading: false, error: null, revision }
      } catch (error) {
        this.changelogs[key] = { data: entry?.data ?? null, loading: false, error: error.message, revision }
      }
    },

    async loadPrTimeline(repoSlug, prId, { force = false } = {}) {
      const revision = useRefreshStore().revision
      const key = prKey(repoSlug, prId)
      const entry = this.prTimelines[key]
      if (!force && isFresh(entry, revision) && (entry.data || entry.loading)) return
      this.prTimelines[key] = { data: entry?.data ?? null, loading: true, error: null, revision }
      try {
        const data = await api.get(
          `/pull-requests/${encodeURIComponent(repoSlug)}/${prId}/timeline`,
        )
        this.prTimelines[key] = { data, loading: false, error: null, revision }
      } catch (error) {
        this.prTimelines[key] = {
          data: entry?.data ?? null,
          loading: false,
          error: error.message,
          revision,
        }
      }
    },

    /** Descarta tudo. O caminho normal é o carimbo de revisão; isto é para trocar de conexão. */
    invalidate() {
      this.issues = {}
      this.changelogs = {}
      this.prTimelines = {}
    },
  },
})
