import { defineStore } from 'pinia'
import { api } from '@/services/api'

export const useHealthStore = defineStore('health', {
  state: () => ({
    api: 'unknown', // unknown | up | down
    database: 'unknown', // unknown | up | down
    version: null,
    checkedAt: null,
  }),
  getters: {
    level: (state) => {
      if (state.api === 'down') return 'down'
      if (state.database === 'down') return 'degraded'
      if (state.api === 'up') return 'ok'
      return 'unknown'
    },
  },
  actions: {
    async check() {
      try {
        const body = await api.get('/health')
        this.api = 'up'
        this.database = body.database.status
        this.version = body.version
      } catch {
        this.api = 'down'
        this.database = 'unknown'
      } finally {
        this.checkedAt = new Date()
      }
    },
  },
})
