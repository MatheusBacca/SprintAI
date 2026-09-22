import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { useNotesStore } from '@/stores/notes'

/**
 * Notificações do app: hoje são os lembretes vencidos ainda não vistos.
 *
 * Antes cada uma virava um cartão flutuante no canto da tela, que cobria o painel
 * da tarefa e o canvas justamente quando havia mais o que ler. Agora elas moram no
 * sino do topo; só sobe para o header o título daquelas que o dev fixa.
 *
 * O que é "fixado" e o que já foi "visto" é preferência de máquina, não dado do
 * lembrete — por isso vai no localStorage, e não num campo novo em `note`. O
 * `pinned` da nota é outra coisa: é o fixar do mural de lembretes.
 */
const PINNED_KEY = 'sprintai.notifications.pinned'
const SEEN_KEY = 'sprintai.notifications.seen'
/** Teto para o que sobra no localStorage de lembrete que nunca mais vence. */
const MAX_REMEMBERED = 50
const DEFAULT_POLL_MS = 30_000

function readIds(key) {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(saved) ? saved.filter((id) => Number.isInteger(id)) : []
  } catch {
    return []
  }
}

function writeIds(key, ids) {
  try {
    localStorage.setItem(key, JSON.stringify(ids.slice(-MAX_REMEMBERED)))
  } catch {
    // Preferência só da sessão: o painel continua funcionando sem o armazenamento.
  }
}

export const useNotificationsStore = defineStore('notifications', {
  state: () => ({
    items: [],
    open: false,
    pinnedIds: readIds(PINNED_KEY),
    seenIds: readIds(SEEN_KEY),
    _timer: null,
  }),
  getters: {
    /** Só o que está no header: fixado que ainda está vencido. */
    pinned: (state) => state.items.filter((note) => state.pinnedIds.includes(note.id)),
    isPinned: (state) => (id) => state.pinnedIds.includes(id),
    unseenCount: (state) => state.items.filter((note) => !state.seenIds.includes(note.id)).length,
  },
  actions: {
    async poll() {
      let due
      try {
        due = await api.get('/notes/reminders/due')
      } catch {
        return // API/banco fora do ar: tenta no próximo ciclo.
      }
      if (!Array.isArray(due)) return
      // Chegou agora = não estava no ciclo anterior. Um lembrete adiado que volta a
      // vencer conta como novo de novo, e é isso que faz o Windows avisar outra vez.
      const conhecidos = new Set(this.items.map((note) => note.id))
      const novos = due.filter((note) => !conhecidos.has(note.id))
      this.items = due

      // Resolvido (concluído ou adiado) sai do "já visto": se voltar, volta a contar.
      const abertos = new Set(due.map((note) => note.id))
      this._setSeen(this.seenIds.filter((id) => abertos.has(id)))

      if (this.open) this.markAllSeen()
      for (const note of novos) this._notifyWindows(note)
    },

    startPolling(everyMs = DEFAULT_POLL_MS) {
      this.stopPolling()
      this.poll()
      this._timer = setInterval(() => this.poll(), everyMs)
    },

    stopPolling() {
      if (this._timer) clearInterval(this._timer)
      this._timer = null
    },

    openPanel() {
      this.open = true
      this.markAllSeen()
    },

    closePanel() {
      this.open = false
    },

    togglePanel() {
      if (this.open) this.closePanel()
      else this.openPanel()
    },

    markAllSeen() {
      this._setSeen(this.items.map((note) => note.id))
    },

    togglePin(id) {
      const pinned = this.pinnedIds.includes(id)
        ? this.pinnedIds.filter((other) => other !== id)
        : [...this.pinnedIds, id]
      this.pinnedIds = pinned.slice(-MAX_REMEMBERED)
      writeIds(PINNED_KEY, this.pinnedIds)
    },

    /**
     * Leva à modal do lembrete — onde dá para mudar o texto, o horário e concluir.
     * É o destino do "Abrir" do painel, do título fixado no header e do clique na
     * notificação do Windows.
     */
    openNote(note) {
      useNotesStore().openEditor(note)
      this.closePanel()
    },

    async acknowledge(id) {
      this._drop(id)
      // Concluído não volta: o fixado morre junto, senão o id ficaria preso no disco.
      if (this.isPinned(id)) this.togglePin(id)
      await useNotesStore()
        .acknowledge(id)
        .catch(() => {})
    },

    async snooze(id, minutes = 10) {
      this._drop(id)
      await useNotesStore()
        .snooze(id, minutes)
        .catch(() => {})
    },

    /** Tira da lista na hora, sem esperar o próximo ciclo redesenhar o painel. */
    _drop(id) {
      this.items = this.items.filter((note) => note.id !== id)
      this._setSeen(this.seenIds.filter((other) => other !== id))
    },

    _setSeen(ids) {
      this.seenIds = ids
      writeIds(SEEN_KEY, ids)
    },

    _notifyWindows(note) {
      if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
      try {
        const aviso = new Notification(note.title || 'Lembrete do SprintAI', {
          body: (note.body || '').slice(0, 180),
          tag: `sprintai-note-${note.id}`,
        })
        aviso.onclick = () => {
          window.focus()
          this.openNote(note)
          aviso.close()
        }
      } catch {
        // Notificações podem estar bloqueadas pelo sistema: o sino no app continua.
      }
    },
  },
})
