import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'

const pad = (n) => String(n).padStart(2, '0')

/** `Date` → `YYYY-MM-DD` no fuso do navegador. */
export function isoDay(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Soma dias a um `YYYY-MM-DD` (meio-dia evita escorregar de dia no horário de verão). */
export function shiftDay(day, days) {
  const date = new Date(`${day}T12:00:00`)
  date.setDate(date.getDate() + days)
  return isoDay(date)
}

export function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null
  } catch {
    return null
  }
}

export const useWeekStore = defineStore('week', {
  state: () => ({
    data: null,
    loading: false,
    error: null,
    _requestId: 0,
  }),
  getters: {
    issueKeys: (state) => {
      const d = state.data
      if (!d) return []
      return [...new Set([...d.without_sprint, ...d.due, ...d.overdue, ...d.slicing].map((i) => i.key))]
    },
  },
  actions: {
    async load(day = null) {
      const requestId = ++this._requestId
      this.loading = true
      this.error = null
      try {
        const data = await api.get(`/week${toQuery({ day, tz: browserTimezone() })}`)
        if (requestId !== this._requestId) return
        if (!Array.isArray(data?.without_sprint)) throw new Error('Resposta inesperada da API da semana.')
        this.data = data
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },
  },
})
