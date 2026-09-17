import { defineStore } from 'pinia'
import { api } from '@/services/api'
import { toQuery } from '@/utils/query'

const EMPTY_DRAFT = () => ({
  id: null,
  issue_key: '',
  kind: 'finding',
  title: '',
  body: '',
  tags: [],
  related_keys: [],
  continues_key: '',
})

export const useContextsStore = defineStore('contexts', {
  state: () => ({
    items: [],
    total: 0,
    loading: false,
    error: null,
    counts: null,
    // incrementa a cada escrita: telas que listam contextos recarregam
    revision: 0,
    editor: { open: false, draft: EMPTY_DRAFT(), saving: false, error: null },
    resolver: { open: false, context: null, issue_key: '', resolution: '', saving: false, error: null },
    _requestId: 0,
  }),
  actions: {
    async list(filters = {}) {
      const requestId = ++this._requestId
      this.loading = true
      this.error = null
      try {
        const result = await api.get(`/contexts${toQuery(filters)}`)
        if (requestId !== this._requestId) return
        this.items = result.items
        this.total = result.total
      } catch (error) {
        if (requestId === this._requestId) this.error = error.message
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    fetch(filters = {}) {
      return api.get(`/contexts${toQuery(filters)}`)
    },

    forIssue(issueKey) {
      return api.get(`/issues/${encodeURIComponent(issueKey)}/contexts`)
    },

    async loadCounts() {
      try {
        this.counts = await api.get('/contexts/counts')
      } catch {
        this.counts = null
      }
    },

    openEditor(context = null, defaults = {}) {
      const draft = context
        ? {
            id: context.id,
            issue_key: context.issue.key,
            kind: context.kind,
            title: context.title,
            body: context.body,
            tags: [...context.tags],
            related_keys: context.relations.filter((r) => r.relation === 'relates').map((r) => r.key),
            continues_key: context.relations.find((r) => r.relation === 'continues')?.key ?? '',
            status: context.status,
          }
        : { ...EMPTY_DRAFT(), ...defaults }
      this.editor = { open: true, draft, saving: false, error: null }
    },

    closeEditor() {
      this.editor.open = false
    },

    async saveEditor() {
      const { draft } = this.editor
      this.editor.saving = true
      this.editor.error = null
      try {
        const continues = draft.continues_key.trim().toUpperCase()
        const relations = [
          ...draft.related_keys.filter((k) => k !== continues).map((issue_key) => ({ issue_key, relation: 'relates' })),
          ...(continues ? [{ issue_key: continues, relation: 'continues' }] : []),
        ]
        const payload = {
          issue_key: draft.issue_key.trim(),
          kind: draft.kind,
          title: draft.title,
          body: draft.body,
          tags: draft.tags,
          relations,
        }
        const saved = draft.id
          ? await api.patch(`/contexts/${draft.id}`, payload)
          : await api.post('/contexts', payload)
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

    async remove(id) {
      await api.delete(`/contexts/${id}`)
      this._changed()
    },

    openResolver(context, issueKey = '') {
      this.resolver = { open: true, context, issue_key: issueKey, resolution: '', saving: false, error: null }
    },

    closeResolver() {
      this.resolver.open = false
    },

    async saveResolver() {
      const r = this.resolver
      r.saving = true
      r.error = null
      try {
        const saved = await api.post(`/contexts/${r.context.id}/resolve`, {
          issue_key: r.issue_key.trim(),
          resolution: r.resolution,
        })
        r.open = false
        this._changed()
        return saved
      } catch (error) {
        r.error = error.message
        return null
      } finally {
        r.saving = false
      }
    },

    async reopen(id) {
      const saved = await api.post(`/contexts/${id}/reopen`)
      this._changed()
      return saved
    },

    _changed() {
      this.revision += 1
    },
  },
})
