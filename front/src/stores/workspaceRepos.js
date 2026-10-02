import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * Repositórios locais (`C:\projects`) e o vínculo de cada um com o Bitbucket. O back lê o
 * disco a cada `load` — não há cache aqui de propósito: a branch atual muda no terminal.
 */
export const useWorkspaceReposStore = defineStore('workspaceRepos', {
  state: () => ({
    root: null,
    repos: [],
    loaded: false,
    loading: false,
    error: null,
    savingSlug: null,
    feedback: null,
  }),
  getters: {
    bySlug: (state) => Object.fromEntries(state.repos.map((repo) => [repo.slug, repo])),
    /** Pastas que existem e têm git — as únicas que viram terminal ou linha do tempo. */
    gitRepos: (state) => state.repos.filter((repo) => repo.present && repo.has_git),
  },
  actions: {
    async load() {
      this.loading = true
      try {
        const data = await api.get('/workspace/repos')
        this.root = data.root
        this.repos = data.repos
        this.loaded = true
        this.error = null
      } catch (error) {
        this.error = error.message
      } finally {
        this.loading = false
      }
    },

    async update(slug, { link, bbSlug, baseBranch }) {
      this.savingSlug = slug
      this.feedback = null
      try {
        const repo = await api.put(`/workspace/repos/${encodeURIComponent(slug)}`, {
          link,
          bb_slug: link === 'manual' ? bbSlug : null,
          base_branch: baseBranch || null,
        })
        this.repos = this.repos.map((r) => (r.slug === slug ? repo : r))
        this.feedback = { type: 'success', slug, text: `${slug} ajustado.` }
        return true
      } catch (error) {
        this.feedback = { type: 'error', slug, text: error.message }
        return false
      } finally {
        this.savingSlug = null
      }
    },
  },
})
