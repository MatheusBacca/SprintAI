import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { useNotificationsStore } from '@/stores/notifications'

/**
 * Filtros de cada sprint (etapas, "Só minhas" e o destaque de status), lembrados por
 * sprint: voltar a uma sprint traz os filtros com que o dev a deixou, e a que nunca foi
 * filtrada abre limpa. É conveniência da máquina, não dado — vai no localStorage.
 */
const FILTERS_KEY = 'sprintai.sprint.filters'
/** As sprints são semanais: as filtradas há mais tempo que isso saem da memória. */
const MAX_REMEMBERED = 40

function readSavedFilters() {
  try {
    const saved = JSON.parse(localStorage.getItem(FILTERS_KEY) ?? '{}')
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}
  } catch {
    return {}
  }
}

function writeSavedFilters(saved) {
  try {
    localStorage.setItem(FILTERS_KEY, JSON.stringify(saved))
  } catch {
    // Sem armazenamento, a memória vale só até recarregar a página.
  }
}

export const useSprintBoardStore = defineStore('sprintBoard', {
  state: () => ({
    sprints: [],
    sprintsLoading: false,
    sprintsError: null,
    tree: null,
    treeLoading: false,
    treeError: null,
    // Os filtros da sprint em tela; trocar de sprint (`enterSprint`) traz os da que entra.
    onlyMine: false,
    /** Etapas ligadas nos chips. */
    stageFilter: [],
    /** Status destacado pelo Alt + clique num card. */
    highlightStatus: null,
    /** A sprint dona dos filtros acima — é nela que `rememberFilters` grava. */
    filtersSprintId: null,
    savedFilters: readSavedFilters(),
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
    /** Troca de sprint: os filtros passam a ser os que a que entra tinha da última vez. */
    enterSprint(sprintId) {
      this.filtersSprintId = sprintId ?? null
      const saved = sprintId ? this.savedFilters[sprintId] : null
      this.stageFilter = Array.isArray(saved?.stages) ? saved.stages.filter((id) => typeof id === 'string') : []
      this.onlyMine = saved?.onlyMine === true
      this.highlightStatus = typeof saved?.highlight === 'string' ? saved.highlight : null
    },

    /**
     * Grava os filtros de agora na sprint em tela. Sem filtro nenhum, a sprint sai da
     * memória — é o mesmo que nunca ter filtrado.
     */
    rememberFilters() {
      const id = this.filtersSprintId
      if (!id) return
      const saved = { ...this.savedFilters }
      delete saved[id]
      if (this.stageFilter.length || this.onlyMine || this.highlightStatus) {
        saved[id] = {
          stages: [...this.stageFilter],
          onlyMine: this.onlyMine,
          highlight: this.highlightStatus,
          at: Date.now(),
        }
      }
      const recent = Object.entries(saved)
        .sort(([, a], [, b]) => (b.at ?? 0) - (a.at ?? 0))
        .slice(0, MAX_REMEMBERED)
      this.savedFilters = Object.fromEntries(recent)
      writeSavedFilters(this.savedFilters)
    },

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
      // A notificação da tarefa no sino vai junto, tenha o card bolinha ou não: um
      // comentário não acende a bolinha, mas abrir o card é ver a novidade.
      useNotificationsStore().markIssueSeen(key)
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
