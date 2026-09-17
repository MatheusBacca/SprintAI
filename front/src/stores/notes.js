import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'

const EMPTY_DRAFT = () => ({
  id: null,
  title: '',
  body: '',
  color: 'yellow',
  tags: [],
  repos: [],
  pinned: false,
  remind_at: null,
  issue_keys: [],
})

export const useNotesStore = defineStore('notes', {
  state: () => ({
    items: [],
    total: 0,
    loading: false,
    error: null,
    tags: [],
    // incrementa a cada criação/edição/exclusão: telas que listam lembretes recarregam
    revision: 0,
    editor: { open: false, draft: EMPTY_DRAFT(), saving: false, error: null },
    // modal global de busca (F4.1): termo inicial e de onde ele veio (selection | issue)
    palette: { open: false, query: '', source: null },
    _requestId: 0,
  }),
  actions: {
    async list(filters = {}) {
      const requestId = ++this._requestId
      this.loading = true
      this.error = null
      try {
        const result = await api.get(`/notes${toQuery(filters)}`)
        if (requestId !== this._requestId) return
        this.items = result.items
        this.total = result.total
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    async fetch(filters = {}) {
      // Consulta avulsa (ex.: aba do painel), sem mexer na lista do mural.
      return api.get(`/notes${toQuery(filters)}`)
    },

    async loadTags() {
      try {
        this.tags = await api.get('/notes/tags')
      } catch {
        this.tags = []
      }
    },

    openEditor(note = null, defaults = {}) {
      const draft = note
        ? {
            id: note.id,
            title: note.title,
            body: note.body,
            color: note.color,
            tags: [...note.tags],
            repos: [...(note.repos ?? [])],
            pinned: note.pinned,
            remind_at: note.remind_at,
            issue_keys: note.issues.map((i) => i.key),
          }
        : { ...EMPTY_DRAFT(), ...defaults }
      this.editor = { open: true, draft, saving: false, error: null }
    },

    openPalette(query = '', source = null) {
      this.palette = { open: true, query, source }
    },

    closePalette() {
      this.palette.open = false
    },

    closeEditor() {
      this.editor.open = false
    },

    async saveEditor() {
      const { draft } = this.editor
      this.editor.saving = true
      this.editor.error = null
      try {
        const payload = {
          title: draft.title,
          body: draft.body,
          color: draft.color,
          tags: draft.tags,
          repos: draft.repos,
          pinned: draft.pinned,
          remind_at: draft.remind_at,
          issue_keys: draft.issue_keys,
        }
        const saved = draft.id
          ? await api.patch(`/notes/${draft.id}`, payload)
          : await api.post('/notes', payload)
        this.editor.open = false
        this._changed()
        return saved
      } catch (error) {
        this.editor.error = error.message
        return null
      } finally {
        this.editor.saving = false
      }
    },

    async patch(id, changes) {
      const saved = await api.patch(`/notes/${id}`, changes)
      this._changed()
      return saved
    },

    async remove(id) {
      await api.delete(`/notes/${id}`)
      this._changed()
    },

    async acknowledge(id) {
      const saved = await api.post(`/notes/${id}/reminder/ack`)
      this._changed()
      return saved
    },

    async snooze(id, minutes = 10) {
      const saved = await api.post(`/notes/${id}/reminder/snooze`, { minutes })
      this._changed()
      return saved
    },

    _changed() {
      this.revision += 1
    },
  },
})
