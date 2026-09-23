import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import { api } from '@/services/api'

/**
 * Ações no Jira a partir das telas — mover o status e mudar os Story Points — e a
 * lista de PRs do badge.
 *
 * Um painel só para o app (`JiraActionPopover`, montado no AppShell) e ancorado no
 * chip clicado. Não mora dentro do card: a árvore da sprint recarrega a cada sync, o
 * Vue Flow remonta os cards, e um painel dentro deles sumiria no meio da escolha.
 *
 * Escrita só sai daqui por gesto explícito do dev (duplo clique no status, Salvar nos
 * pontos): é a regra proposta → confirmação → ação, uma tarefa por vez.
 */

function rectOf(element) {
  const rect = element?.getBoundingClientRect?.()
  if (!rect) return null
  const { top, left, right, bottom, width, height } = rect
  return { top, left, right, bottom, width, height }
}

function path(key, suffix) {
  return `/issues/${encodeURIComponent(key)}/${suffix}`
}

export const useJiraActionsStore = defineStore('jiraActions', {
  state: () => ({
    /** `{ kind: 'status' | 'points' | 'prs', issueKey, anchor, rect, points?, links? }` */
    open: null,
    flow: { key: null, data: null, loading: false, error: null },
    saving: false,
    error: null,
    /** Última escrita desta aba: o AppShell recarrega as telas a partir dela. */
    lastWrite: null,
  }),
  actions: {
    openStatus(issueKey, anchor) {
      if (this._open({ kind: 'status', issueKey }, anchor)) this.loadFlow(issueKey)
    },

    openPoints(issueKey, anchor, points = null) {
      this._open({ kind: 'points', issueKey, points }, anchor)
    },

    openPullRequests(links, anchor, issueKey = null) {
      this._open({ kind: 'prs', issueKey, links }, anchor)
    },

    /** Clicar de novo no mesmo chip fecha — é o que o dev espera de um menu. */
    _open(entry, anchor) {
      if (this.open && anchor && this.open.anchor === anchor && this.open.kind === entry.kind) {
        this.close()
        return false
      }
      this.error = null
      this.saving = false
      // O elemento fica cru: reativo, o Vue tentaria embrulhar o DOM inteiro num proxy.
      this.open = { ...entry, anchor: anchor ? markRaw(anchor) : null, rect: rectOf(anchor) }
      return true
    },

    close() {
      this.open = null
      this.error = null
      this.saving = false
    },

    async loadFlow(issueKey) {
      this.flow = { key: issueKey, data: null, loading: true, error: null }
      try {
        const data = await api.get(path(issueKey, 'transitions'))
        if (this.flow.key === issueKey) this.flow = { key: issueKey, data, loading: false, error: null }
      } catch (error) {
        if (this.flow.key === issueKey) {
          this.flow = { key: issueKey, data: null, loading: false, error: error.message }
        }
      }
    },

    transition(issueKey, transitionId) {
      return this._write(() => api.post(path(issueKey, 'transitions'), { transition_id: transitionId }))
    },

    savePoints(issueKey, storyPoints) {
      return this._write(() => api.put(path(issueKey, 'story-points'), { story_points: storyPoints }))
    },

    async _write(call) {
      if (this.saving) return null
      this.saving = true
      this.error = null
      try {
        const result = await call()
        this.lastWrite = { id: result.write_id, key: result.issue_key, at: Date.now() }
        this.close()
        return result
      } catch (error) {
        // O painel continua aberto com o erro: o dev decide se tenta de novo ou vai ao Jira.
        this.error = error.message
        return null
      } finally {
        this.saving = false
      }
    },
  },
})
