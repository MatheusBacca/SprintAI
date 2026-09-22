import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { useNotesStore } from '@/stores/notes'

/**
 * Notificações do app: os lembretes vencidos ainda não vistos e as tarefas da sprint
 * ativa em que outra pessoa mexeu nas últimas 48h.
 *
 * Antes cada lembrete virava um cartão flutuante no canto da tela, que cobria o painel
 * da tarefa e o canvas justamente quando havia mais o que ler. Agora as duas fontes
 * moram no sino do topo; só sobe para o header o título do lembrete que o dev fixa.
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

/** Os botões de filtro do painel, na ordem em que aparecem. */
export const NOTIFICATION_KINDS = [
  { id: 'reminder', label: 'Lembretes' },
  { id: 'update', label: 'Tarefas' },
]

/**
 * Id de uma notificação na lista — é por ele que "visto" e "fixado" lembram de cada
 * uma. O da tarefa carrega o horário da última mexida: mexida nova é notificação nova,
 * e o selo volta a contar mesmo com a tarefa já na lista.
 */
const reminderId = (id) => `lembrete:${id}`
const updateId = (update) => `tarefa:${update.sprint_id}:${update.key}@${update.occurred_at}`

function readIds(key) {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (!Array.isArray(saved)) return []
    // Antes de as tarefas entrarem no sino, o id guardado era o número do lembrete.
    return saved
      .map((id) => (Number.isInteger(id) ? reminderId(id) : id))
      .filter((id) => typeof id === 'string')
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
    reminders: [],
    updates: [],
    open: false,
    /** Tipos ligados nos botões do painel; vazia = sem filtro, mostra tudo. */
    kinds: [],
    pinnedIds: readIds(PINNED_KEY),
    seenIds: readIds(SEEN_KEY),
    _timer: null,
  }),
  getters: {
    /**
     * A lista do painel. Lembrete é cobrança e tarefa é notícia: os lembretes vêm
     * primeiro (do mais vencido para o menos), e só então as mexidas, da mais recente
     * para a mais antiga. Uma ordem só pelo horário enterraria o lembrete de ontem
     * embaixo do que aconteceu há cinco minutos.
     */
    entries: (state) => [
      ...state.reminders.map((note) => ({ id: reminderId(note.id), kind: 'reminder', note })),
      ...state.updates.map((update) => ({ id: updateId(update), kind: 'update', update })),
    ],
    /** O que o filtro deixa passar — é o que a lista mostra. */
    visible() {
      return this.kinds.length
        ? this.entries.filter((entry) => this.kinds.includes(entry.kind))
        : this.entries
    },
    counts: (state) => ({ reminder: state.reminders.length, update: state.updates.length }),
    /** Só o que está no header: lembrete fixado que ainda está vencido. */
    pinned() {
      return this.entries.filter(
        (entry) => entry.kind === 'reminder' && this.pinnedIds.includes(entry.id),
      )
    },
    isPinned: (state) => (id) => state.pinnedIds.includes(id),
    unseenCount() {
      return this.entries.filter((entry) => !this.seenIds.includes(entry.id)).length
    },
  },
  actions: {
    async poll() {
      // Uma fonte fora do ar não pode zerar a outra: o sino mostra o que conseguiu ler.
      const [due, updates] = await Promise.all([
        api.get('/notes/reminders/due').catch(() => null),
        api.get('/notifications/updates').catch(() => null),
      ])
      // Chegou agora = não estava no ciclo anterior. Um lembrete adiado que volta a
      // vencer conta como novo de novo, e é isso que faz o Windows avisar outra vez.
      const conhecidos = new Set(this.reminders.map((note) => note.id))
      const novos = Array.isArray(due) ? due.filter((note) => !conhecidos.has(note.id)) : []
      if (Array.isArray(due)) this.reminders = due
      if (Array.isArray(updates?.updates)) this.updates = updates.updates

      // Resolvido (concluído ou adiado) sai do "já visto": se voltar, volta a contar.
      // Mexida que envelheceu para fora da janela some pelo mesmo caminho.
      const abertas = new Set(this.entries.map((entry) => entry.id))
      this._setSeen(this.seenIds.filter((id) => abertas.has(id)))

      if (this.open) this.markAllSeen()
      // Só lembrete toca no Windows: a primeira leitura traz 48h de mexidas de uma vez,
      // e isso viraria uma saraivada de avisos do sistema por algo que já passou.
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

    /** Liga e desliga um tipo no filtro; desligar o último volta a mostrar tudo. */
    toggleKind(kind) {
      this.kinds = this.kinds.includes(kind)
        ? this.kinds.filter((other) => other !== kind)
        : [...this.kinds, kind]
    },

    /**
     * Visto é o que apareceu na tela: com um filtro ligado, o que ele escondeu continua
     * somando no selo. Marcar tudo apagaria em silêncio a novidade que o dev não viu.
     */
    markAllSeen() {
      const vistas = new Set(this.seenIds)
      for (const entry of this.visible) vistas.add(entry.id)
      this._setSeen([...vistas])
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
      if (this.isPinned(reminderId(id))) this.togglePin(reminderId(id))
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
      this.reminders = this.reminders.filter((note) => note.id !== id)
      this._setSeen(this.seenIds.filter((other) => other !== reminderId(id)))
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
