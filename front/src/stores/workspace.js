import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { useNotificationsStore } from '@/stores/notifications'

/**
 * Workspaces: a feature aberta numa aba da tela Workspace, com a árvore dos cards e os
 * repositórios envolvidos. Store próprio — usar o `sprintBoard` faria a árvore de uma tela
 * sobrescrever a da outra.
 */
export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    list: [],
    listLoaded: false,
    listError: null,
    currentId: null,
    detail: null,
    detailError: null,
    detailLoading: false,
    tree: null,
    treeError: null,
    treeLoading: false,
    opening: false,
    openError: null,
    actionError: null,
    _detailRequest: 0,
    _treeRequest: 0,
  }),
  getters: {
    /** Abas abertas, na ordem em que foram abertas. */
    tabs: (state) => state.list.filter((w) => w.is_open).sort((a, b) => a.tab_order - b.tab_order),
    closed: (state) => state.list.filter((w) => !w.is_open),
    current: (state) => state.list.find((w) => w.id === state.currentId) ?? state.detail?.workspace ?? null,
    /** Repos que a tela mostra: os escondidos ficam à parte, para poder trazer de volta. */
    visibleRepos: (state) => (state.detail?.repos ?? []).filter((r) => !r.hidden),
    hiddenRepos: (state) => (state.detail?.repos ?? []).filter((r) => r.hidden),
  },
  actions: {
    async loadList() {
      try {
        this.list = await api.get('/workspaces')
        this.listLoaded = true
        this.listError = null
      } catch (error) {
        this.listError = error.message
      }
    },

    /** Abre (ou reabre) o workspace de uma tarefa. Devolve o workspace, ou `null` se falhou. */
    async openIssue(issueKey) {
      return this._open({ root_issue_key: issueKey })
    },

    async openFree(title, repos = []) {
      return this._open({ title, repos })
    },

    async _open(payload) {
      this.opening = true
      this.openError = null
      try {
        const workspace = await api.post('/workspaces', payload)
        await this.loadList()
        return workspace
      } catch (error) {
        this.openError = error.message
        return null
      } finally {
        this.opening = false
      }
    },

    /** Fechar a aba não apaga o workspace: ele volta para "Abertos antes". */
    async close(id) {
      try {
        await api.patch(`/workspaces/${id}`, { is_open: false })
        await this.loadList()
      } catch (error) {
        this.actionError = error.message
      }
    },

    async reopen(id) {
      try {
        await api.patch(`/workspaces/${id}`, { is_open: true })
        await this.loadList()
      } catch (error) {
        this.actionError = error.message
      }
    },

    async remove(id) {
      try {
        await api.delete(`/workspaces/${id}`)
        if (this.currentId === id) this.select(null)
        await this.loadList()
      } catch (error) {
        this.actionError = error.message
      }
    },

    select(id) {
      if (this.currentId === id) return
      this.currentId = id
      this.detail = null
      this.detailError = null
      this.tree = null
      this.treeError = null
    },

    async loadDetail(id = this.currentId) {
      if (!id) return
      const request = ++this._detailRequest
      this.detailLoading = true
      try {
        const detail = await api.get(`/workspaces/${id}`)
        if (request === this._detailRequest && id === this.currentId) {
          this.detail = detail
          this.detailError = null
        }
      } catch (error) {
        if (request === this._detailRequest) this.detailError = error.message
      } finally {
        if (request === this._detailRequest) this.detailLoading = false
      }
    },

    async loadTree(id = this.currentId) {
      if (!id) return
      const request = ++this._treeRequest
      this.treeLoading = true
      try {
        const tree = await api.get(`/workspaces/${id}/tree`)
        if (request === this._treeRequest && id === this.currentId) {
          this.tree = tree
          this.treeError = null
        }
      } catch (error) {
        if (request === this._treeRequest) {
          this.tree = null
          this.treeError = error.message
        }
      } finally {
        if (request === this._treeRequest) this.treeLoading = false
      }
    },

    /** `add` fixa, `hide` esconde, `auto` volta ao que a descoberta diz. */
    async pin(slug, mode) {
      const id = this.currentId
      if (!id) return
      try {
        await api.put(`/workspaces/${id}/repos/${encodeURIComponent(slug)}`, { mode })
        await this.loadDetail(id)
      } catch (error) {
        this.actionError = error.message
      }
    },

    /** Abre a pasta no VS Code (`ide`) ou no Windows Terminal (`terminal`). */
    async openFolder(target, path) {
      this.actionError = null
      try {
        await api.post('/workspace/open', { target, path })
        return true
      } catch (error) {
        this.actionError = error.message
        return false
      }
    },

    /** Mesmo gesto do canvas da Sprint: abrir o card apaga a bolinha de atualização. */
    async markSeen(key) {
      // A notificação da tarefa no sino vai junto, tenha o card bolinha ou não: um
      // comentário não acende a bolinha, mas abrir o card é ver a novidade.
      useNotificationsStore().markIssueSeen(key)
      const node = this.tree?.nodes.find((n) => n.key === key)
      if (!node?.unseen_changes?.length) return
      node.unseen_changes = []
      try {
        await api.post(`/issues/${encodeURIComponent(key)}/seen`)
      } catch {
        // Falhar só faz a bolinha voltar na próxima carga — não vale erro na tela.
      }
    },
  },
})
