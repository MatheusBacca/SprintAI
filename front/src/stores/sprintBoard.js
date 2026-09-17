import { defineStore } from 'pinia'
import { api } from '@/services/api'

export const useSprintBoardStore = defineStore('sprintBoard', {
  state: () => ({
    sprints: [],
    sprintsLoading: false,
    sprintsError: null,
    tree: null,
    treeLoading: false,
    treeError: null,
    onlyMine: false,
    _requestId: 0,
  }),
  getters: {
    grouped: (state) => ({
      active: state.sprints.filter((s) => s.state === 'active'),
      future: state.sprints.filter((s) => s.state === 'future'),
      closed: state.sprints.filter((s) => s.state === 'closed'),
    }),
    defaultSprintId: (state) => {
      const pick = (st) => state.sprints.find((s) => s.state === st && s.issue_count > 0)
      return (pick('active') ?? pick('future') ?? state.sprints[0])?.id ?? null
    },
  },
  actions: {
    async loadSprints() {
      this.sprintsLoading = true
      this.sprintsError = null
      try {
        this.sprints = await api.get('/sprints')
      } catch (error) {
        this.sprintsError = error.message
      } finally {
        this.sprintsLoading = false
      }
    },

    async loadTree(sprintId) {
      // Troca rápida de sprint: só a última resposta vale.
      const requestId = ++this._requestId
      this.treeLoading = true
      this.treeError = null
      try {
        const query = this.onlyMine ? '?only_mine=true' : ''
        const tree = await api.get(`/sprints/${sprintId}/tree${query}`)
        if (requestId === this._requestId) this.tree = tree
      } catch (error) {
        if (requestId === this._requestId) {
          this.tree = null
          this.treeError = error.message
        }
      } finally {
        if (requestId === this._requestId) this.treeLoading = false
      }
    },

    /**
     * O dev abriu o card: a bolinha de atualização some na hora e o back refaz a foto
     * do que foi visto. Falhar em gravar só faz a bolinha voltar na próxima carga da
     * árvore — não vale um erro na tela.
     */
    async markSeen(key) {
      const node = this.tree?.nodes.find((n) => n.key === key)
      if (!node?.unseen_changes?.length) return
      node.unseen_changes = []
      try {
        await api.post(`/issues/${encodeURIComponent(key)}/seen`)
      } catch {
        // proposital: ver o comentário acima
      }
    },
  },
})
