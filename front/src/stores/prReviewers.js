import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * Reviewers dos PRs pelo SprintAI. A lista de quem pode entrar são os membros do workspace do
 * Bitbucket (o back guarda por meia hora; aqui, a sessão). A troca só sai depois da
 * confirmação na tela, e o sync que o back chama em seguida leva a lista nova ao espelho.
 */
export const usePrReviewersStore = defineStore('prReviewers', {
  state: () => ({
    members: [],
    membersLoaded: false,
    membersLoading: false,
    membersError: null,
    /** `{ 'repo#id': true }` — o PR com troca em andamento. */
    saving: {},
  }),
  actions: {
    async loadMembers({ refresh = false } = {}) {
      if ((this.membersLoaded && !refresh) || this.membersLoading) return
      this.membersLoading = true
      this.membersError = null
      try {
        const data = await api.get(`/bitbucket/members${refresh ? '?refresh=true' : ''}`)
        this.members = data.members
        this.membersLoaded = true
      } catch (error) {
        this.membersError = error.message
      } finally {
        this.membersLoading = false
      }
    },

    /** Põe e tira reviewers. Devolve a lista nova (`reviewers`) ou lança o erro do back. */
    async update(repoSlug, prId, { add = [], remove = [] }) {
      const id = `${repoSlug}#${prId}`
      this.saving = { ...this.saving, [id]: true }
      try {
        const path = `/pull-requests/${encodeURIComponent(repoSlug)}/${prId}/reviewers`
        return await api.put(path, { add, remove })
      } finally {
        const rest = { ...this.saving }
        delete rest[id]
        this.saving = rest
      }
    },
  },
})
