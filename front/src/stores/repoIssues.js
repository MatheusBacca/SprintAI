import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * Menu "WAIs por repositório" do topo: as tarefas de cada repo na sprint anterior, na atual
 * e na próxima. Quem diz o repo de cada tarefa é o back (branch com a chave, PR do Bitbucket
 * ou `[repo]` do título), e também o projeto do Bitbucket de cada repo (OrganIA, weon) — o
 * mesmo agrupamento com que o dev escolheu os repos em Configurações › Sincronização.
 *
 * O repo e o projeto escolhidos são conveniência da máquina, não dado: vão no localStorage.
 */
const SELECTED_KEY = 'sprintai.repoIssues.repo'
const PROJECT_KEY = 'sprintai.repoIssues.project'

/** Os segmentos que não são um projeto do Bitbucket. */
export const ALL_PROJECTS = '*'
export const NO_PROJECT = '-'

function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Sem armazenamento a escolha vale só até recarregar a página.
  }
}

const projectOf = (repo) => repo.project_key ?? NO_PROJECT

export const useRepoIssuesStore = defineStore('repoIssues', {
  state: () => ({
    open: false,
    repos: [],
    loading: false,
    loaded: false,
    error: null,
    selected: read(SELECTED_KEY),
    project: read(PROJECT_KEY) ?? ALL_PROJECTS,
    _requestId: 0,
  }),
  getters: {
    /**
     * Os segmentos do topo do painel: um por projeto, na ordem do nome, e "Outros" no fim
     * para o repo fora do sync (que só aparece pela branch ou pelo título).
     */
    projects: (state) => {
      const byKey = new Map()
      for (const repo of state.repos) {
        const key = projectOf(repo)
        const entry = byKey.get(key) ?? { key, name: repo.project_name ?? 'Outros', keys: new Set() }
        // WAI em dois repos do mesmo projeto (`[supervisor / weaction-api]`) conta uma vez.
        for (const sprint of repo.sprints) for (const issue of sprint.issues) entry.keys.add(issue.key)
        byKey.set(key, entry)
      }
      const projects = [...byKey.values()].map(({ keys, ...project }) => ({ ...project, count: keys.size }))
      const named = projects.filter((p) => p.key !== NO_PROJECT)
      named.sort((a, b) => a.name.localeCompare(b.name, 'pt-BR', { sensitivity: 'base' }))
      return [...named, ...projects.filter((p) => p.key === NO_PROJECT)]
    },
    /** O projeto escolhido; o lembrado que sumiu (saiu do sync) volta para "Todos". */
    activeProject() {
      return this.projects.some((p) => p.key === this.project) ? this.project : ALL_PROJECTS
    },
    /** Os repos do segmento escolhido, agrupados pelo projeto na ordem dos segmentos. */
    visibleRepos() {
      const order = this.projects.map((p) => p.key)
      const repos =
        this.activeProject === ALL_PROJECTS
          ? this.repos
          : this.repos.filter((repo) => projectOf(repo) === this.activeProject)
      return [...repos].sort((a, b) => order.indexOf(projectOf(a)) - order.indexOf(projectOf(b)))
    },
    /** O repo escolhido; o lembrado que não está no segmento cai no primeiro dele. */
    current() {
      return this.visibleRepos.find((repo) => repo.slug === this.selected) ?? this.visibleRepos[0] ?? null
    },
  },
  actions: {
    async load() {
      const requestId = ++this._requestId
      this.loading = true
      try {
        const result = await api.get('/workspace/repo-issues')
        if (requestId !== this._requestId) return
        this.repos = result?.repos ?? []
        this.error = null
        this.loaded = true
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    /** Abrir sempre relê: o painel fechado não acompanha o `refresh.revision`. */
    openPanel() {
      this.open = true
      this.load()
    },

    closePanel() {
      this.open = false
    },

    togglePanel() {
      if (this.open) this.closePanel()
      else this.openPanel()
    },

    select(slug) {
      this.selected = slug
      write(SELECTED_KEY, slug)
    },

    selectProject(key) {
      this.project = key
      write(PROJECT_KEY, key)
    },
  },
})
