import { defineStore } from 'pinia'
import { api } from '@/services/api'

/**
 * A branch aberta em cada pasta de terminal (`POST /workspace/heads`). O back só lê o `HEAD`,
 * sem rodar git, então a tela pergunta de tempos em tempos: um `git switch` digitado no
 * terminal aparece no cabeçalho em seguida. A troca pela linha do tempo pede na hora.
 */
export const useGitHeadsStore = defineStore('gitHeads', {
  state: () => ({
    /** `{ [cwd]: { branch, detached, commit, is_repo } }` — a chave é o `cwd` da sessão. */
    heads: {},
    paths: [],
    _request: 0,
  }),
  actions: {
    /** As pastas dos terminais na tela. Mudou a lista, pergunta na hora. */
    track(paths) {
      const next = [...new Set(paths)].sort()
      if (next.join('|') === this.paths.join('|')) return Promise.resolve()
      this.paths = next
      return this.refresh()
    },

    async refresh() {
      if (!this.paths.length) return
      const request = ++this._request
      try {
        const data = await api.post('/workspace/heads', { paths: this.paths })
        if (request !== this._request) return
        this.heads = Object.fromEntries(data.heads.map((h) => [h.path, h]))
      } catch {
        // Uma consulta perdida não vale erro na tela: a próxima acerta.
      }
    },
  },
})
