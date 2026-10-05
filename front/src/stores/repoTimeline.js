import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { useGitHeadsStore } from '@/stores/gitHeads'

const PAGE = 300

/**
 * Linha do tempo das branches de um repo local (`GET /workspace/repos/{slug}/graph`).
 *
 * O dado é do git local, não do espelho: não segue o `refresh.revision`, segue a
 * impressão digital do `.git`. A tela pergunta a cada poucos segundos com `since` e, sem
 * mudança, o back devolve só as worktrees (as alterações não commitadas).
 *
 * O painel de branches (`/refs`) traz todas as refs — o grafo só manda as que etiquetam a
 * página. As quatro escritas (fetch --prune, avançar, apagar branch local e trocar a branch do
 * clone) são gesto do dev; depois de cada uma, grafo e painel se refazem.
 */
export const useRepoTimelineStore = defineStore('repoTimeline', {
  state: () => ({
    repo: null,
    scope: 'feature',
    keys: [],
    graph: null,
    commits: [],
    refs: [],
    loading: false,
    loadingMore: false,
    error: null,
    selectedSha: null,
    detail: null,
    detailLoading: false,
    detailError: null,
    /** `{ 'WAI-1': { status, status_label } }` somado de todas as respostas — a cor das chaves. */
    issueStatus: {},
    panel: { refs: [], loaded: false, loading: false, error: null },
    query: '',
    searchResults: null,
    searching: false,
    fetching: false,
    busyBranch: null,
    /** `{ type: 'success' | 'error', text, code?, branch? }` da última ação. */
    feedback: null,
    /** `{ sha, at }` — o grafo rola até o commit. */
    scrollTo: null,
    panelRepo: null,
    _request: 0,
    _searchRequest: 0,
    _polling: false,
  }),
  getters: {
    worktrees: (state) => state.graph?.worktrees ?? [],
    hasMore: (state) => Boolean(state.graph?.has_more),
  },
  actions: {
    _query({ skip = 0, since = null } = {}) {
      const params = new URLSearchParams({ scope: this.scope, limit: String(PAGE), skip: String(skip) })
      for (const key of this.keys) params.append('keys', key)
      if (since) params.set('since', since)
      return `/workspace/repos/${encodeURIComponent(this.repo)}/graph?${params}`
    },

    /** Troca de repo, de escopo ou de chaves: desenho novo. O mesmo pedido de novo só recarrega. */
    async load(repo, { scope = this.scope, keys = this.keys } = {}) {
      const changed = repo !== this.repo || scope !== this.scope || keys.join() !== this.keys.join()
      this.repo = repo
      this.scope = scope
      this.keys = [...keys]
      if (changed) {
        this.graph = null
        this.commits = []
        this.refs = []
        this.selectedSha = null
        this.detail = null
        if (repo !== this.panelRepo) {
          this.panel = { refs: [], loaded: false, loading: false, error: null }
          this.query = ''
          this.searchResults = null
          this.feedback = null
        }
      }
      if (!repo) return
      const request = ++this._request
      this.loading = true
      try {
        const graph = await api.get(this._query())
        if (request !== this._request) return
        this._apply(graph, { append: false })
        this.error = null
      } catch (error) {
        if (request === this._request) this.error = error.message
      } finally {
        if (request === this._request) this.loading = false
      }
    },

    async loadMore() {
      if (!this.repo || !this.hasMore || this.loadingMore) return
      const request = this._request
      this.loadingMore = true
      try {
        const graph = await api.get(this._query({ skip: this.commits.length }))
        if (request === this._request) this._apply(graph, { append: true })
      } catch (error) {
        this.error = error.message
      } finally {
        this.loadingMore = false
      }
    },

    /**
     * Pergunta se o `.git` mudou. Sem mudança, só as worktrees andam. Com mudança, volta
     * para a primeira página — um commit novo entra no topo.
     */
    async poll() {
      // Navegador com a janela atrás de outra junta os timers e dispara vários de uma vez:
      // com uma consulta no ar, as outras não saem.
      if (!this.repo || !this.graph || this.loading || this._polling) return
      const request = this._request
      this._polling = true
      try {
        const graph = await api.get(this._query({ since: this.graph.fingerprint }))
        if (request !== this._request) return
        if (graph.unchanged) this.graph = { ...this.graph, worktrees: graph.worktrees }
        else {
          this._apply(graph, { append: false })
          // O `.git` mudou (commit, checkout, fetch no terminal): o painel também.
          if (this.panel.loaded) this.loadRefs()
        }
      } catch {
        // Uma consulta perdida não vale erro na tela: a próxima tenta de novo.
      } finally {
        this._polling = false
      }
    },

    _apply(graph, { append }) {
      this._mergeStatus(graph.issue_status)
      if (append) {
        const known = new Set(this.refs.map((r) => `${r.kind}:${r.name}`))
        this.commits = [...this.commits, ...graph.commits]
        this.refs = [...this.refs, ...graph.refs.filter((r) => !known.has(`${r.kind}:${r.name}`))]
        this.graph = { ...graph, refs: this.refs, commits: this.commits }
        return
      }
      this.commits = graph.commits
      this.refs = graph.refs
      this.graph = graph
    },

    _mergeStatus(status) {
      if (status && Object.keys(status).length) this.issueStatus = { ...this.issueStatus, ...status }
    },

    _base() {
      return `/workspace/repos/${encodeURIComponent(this.repo)}`
    },

    // --- Painel de branches -------------------------------------------------------------

    async loadRefs() {
      const repo = this.repo
      if (!repo) return
      this.panel = { ...this.panel, loading: true }
      try {
        const params = new URLSearchParams()
        for (const key of this.keys) params.append('keys', key)
        const data = await api.get(`${this._base()}/refs?${params}`)
        if (repo !== this.repo) return
        this._mergeStatus(data.issue_status)
        this.panel = { refs: data.refs, loaded: true, loading: false, error: null }
        this.panelRepo = repo
      } catch (error) {
        if (repo === this.repo) this.panel = { ...this.panel, loading: false, error: error.message }
      }
    },

    /** Busca no histórico inteiro do repo (mensagem, autor, hash). Só a última resposta vale. */
    async search(query) {
      this.query = query
      const text = query.trim()
      if (text.length < 2 || !this.repo) {
        this.searchResults = null
        this.searching = false
        return
      }
      const request = ++this._searchRequest
      this.searching = true
      try {
        const data = await api.get(`${this._base()}/search?q=${encodeURIComponent(text)}`)
        if (request !== this._searchRequest) return
        this._mergeStatus(data.issue_status)
        this.searchResults = data
      } catch (error) {
        if (request === this._searchRequest) this.searchResults = { query: text, commits: [], error: error.message }
      } finally {
        if (request === this._searchRequest) this.searching = false
      }
    },

    /** Abre o commit no detalhe e rola o grafo até ele (se estiver na página carregada). */
    focusCommit(sha) {
      this.scrollTo = { sha, at: Date.now() }
      return this.selectCommit(sha)
    },

    async _afterWrite() {
      await Promise.all([this.load(this.repo), this.loadRefs()])
    },

    /** `git fetch origin --prune`: só pelo botão, nunca sozinho. */
    async fetchRemote() {
      if (!this.repo || this.fetching) return
      this.fetching = true
      this.feedback = null
      try {
        const result = await api.post(`${this._base()}/fetch`)
        const parts = [
          result.added.length && `${result.added.length} nova(s)`,
          result.updated.length && `${result.updated.length} atualizada(s)`,
          result.pruned.length && `${result.pruned.length} removida(s) do remoto`,
          result.tags.length && `${result.tags.length} tag(s)`,
        ].filter(Boolean)
        this.feedback = { type: 'success', text: parts.length ? `Fetch: ${parts.join(', ')}.` : 'Fetch: nada mudou no Bitbucket.' }
        await this._afterWrite()
      } catch (error) {
        this.feedback = { type: 'error', text: error.message, code: error.body?.code }
      } finally {
        this.fetching = false
      }
    },

    /** Fast-forward da branch local até o upstream. */
    async updateBranch(name) {
      this.busyBranch = name
      this.feedback = null
      try {
        const result = await api.post(`${this._base()}/branches/update`, { name })
        this.feedback = {
          type: 'success',
          branch: name,
          text: result.mode === 'noop' ? `${name} já estava em dia.` : `${name} avançou até o upstream.`,
        }
        await this._afterWrite()
        return true
      } catch (error) {
        this.feedback = { type: 'error', branch: name, text: error.message, code: error.body?.code }
        return false
      } finally {
        this.busyBranch = null
      }
    },

    /** Apaga a branch local. `force` (`-D`) só depois da segunda confirmação da tela. */
    async deleteBranch(name, { force = false } = {}) {
      this.busyBranch = name
      this.feedback = null
      try {
        const result = await api.post(`${this._base()}/branches/delete`, { name, force })
        this.feedback = {
          type: 'success',
          branch: name,
          text: `${name} apagada. Para desfazer: git branch ${name} ${result.target.slice(0, 10)}`,
        }
        await this._afterWrite()
        return { ok: true }
      } catch (error) {
        const code = error.body?.code
        this.feedback = { type: 'error', branch: name, text: error.message, code }
        return { ok: false, code }
      } finally {
        this.busyBranch = null
      }
    },

    /**
     * Abre a branch no clone principal (`git switch`, sem `--force`). `origin/x` sem local
     * vira `x` acompanhando o origin. Os terminais do repo releem a branch na hora.
     */
    async switchBranch(name) {
      this.busyBranch = name
      this.feedback = null
      try {
        const result = await api.post(`${this._base()}/branches/switch`, { name })
        this.feedback = {
          type: 'success',
          branch: result.name,
          text: result.created
            ? `${result.name} criada a partir de ${name} e aberta no clone.`
            : result.previous === result.name
              ? `${result.name} já estava aberta no clone.`
              : `Clone agora em ${result.name}${result.previous ? ` (antes: ${result.previous})` : ''}.`,
        }
        useGitHeadsStore().refresh()
        await this._afterWrite()
        return { ok: true }
      } catch (error) {
        const code = error.body?.code
        this.feedback = { type: 'error', branch: name, text: error.message, code }
        return { ok: false, code }
      } finally {
        this.busyBranch = null
      }
    },

    async selectCommit(sha) {
      this.selectedSha = sha
      this.detail = null
      this.detailError = null
      if (!sha || !this.repo) return
      this.detailLoading = true
      try {
        const detail = await api.get(`/workspace/repos/${encodeURIComponent(this.repo)}/commits/${sha}`)
        if (this.selectedSha === sha) this.detail = detail
      } catch (error) {
        if (this.selectedSha === sha) this.detailError = error.message
      } finally {
        if (this.selectedSha === sha) this.detailLoading = false
      }
    },
  },
})
