import { defineStore } from 'pinia'
import { api } from '@/services/api'

function emptyStatus(provider) {
  return { provider, configured: false, settings: {} }
}

export const useConnectionsStore = defineStore('connections', {
  state: () => ({
    byProvider: { jira: emptyStatus('jira'), bitbucket: emptyStatus('bitbucket') },
    loading: false,
    loadError: null,
    // Por provedor: 'saving' | 'testing' | 'removing' | null
    busy: { jira: null, bitbucket: null },
    // Por provedor: { type: 'success' | 'error', text }
    feedback: { jira: null, bitbucket: null },
  }),
  getters: {
    jira: (state) => state.byProvider.jira,
    bitbucket: (state) => state.byProvider.bitbucket,
  },
  actions: {
    async load() {
      this.loading = true
      this.loadError = null
      try {
        const list = await api.get('/connections')
        for (const status of list) this.byProvider[status.provider] = status
      } catch (error) {
        this.loadError = error.message
      } finally {
        this.loading = false
      }
    },

    async save(provider, payload) {
      return this._run(provider, 'saving', async () => {
        const status = await api.put(`/connections/${provider}`, payload)
        this.byProvider[provider] = status
        return { type: 'success', text: `Conectado como ${status.account_name}. Chave salva no Cofre do Windows.` }
      })
    },

    async test(provider) {
      return this._run(provider, 'testing', async () => {
        const result = await api.post(`/connections/${provider}/test`)
        this.byProvider[provider] = result.status
        return result.ok
          ? { type: 'success', text: `Conexão ok — ${result.status.account_name}.` }
          : { type: 'error', text: result.message }
      })
    },

    async remove(provider) {
      return this._run(provider, 'removing', async () => {
        await api.delete(`/connections/${provider}`)
        this.byProvider[provider] = emptyStatus(provider)
        return { type: 'success', text: 'Conexão removida do Cofre do Windows.' }
      })
    },

    async _run(provider, kind, fn) {
      this.busy[provider] = kind
      this.feedback[provider] = null
      try {
        this.feedback[provider] = await fn()
        return this.feedback[provider].type === 'success'
      } catch (error) {
        this.feedback[provider] = { type: 'error', text: error.message }
        return false
      } finally {
        this.busy[provider] = null
      }
    },
  },
})
