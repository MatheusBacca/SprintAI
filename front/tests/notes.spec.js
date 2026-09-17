import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import IssueNotesTab from '@/components/issue/IssueNotesTab.vue'
import LinksField from '@/components/notes/LinksField.vue'
import MentionTextarea from '@/components/notes/MentionTextarea.vue'
import NoteCard from '@/components/notes/NoteCard.vue'
import NoteEditor from '@/components/notes/NoteEditor.vue'
import ReminderCenter from '@/components/notes/ReminderCenter.vue'
import NotesView from '@/views/NotesView.vue'
import { routes } from '@/router/routes'
import { useNotesStore } from '@/stores/notes'
import { fromLocalInput, reminderPresets, toLocalInput } from '@/utils/datetime'
import { mentionParts, mentionsIn } from '@/utils/noteTokens'

const NOW = new Date()

function note(id, extra = {}) {
  return {
    id,
    title: `Nota ${id}`,
    body: 'Lembrar do retry exponencial',
    color: 'yellow',
    tags: [],
    pinned: false,
    archived: false,
    remind_at: null,
    reminded_at: null,
    reminder_due: false,
    created_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
    issues: [],
    rank: null,
    ...extra,
  }
}

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

let calls
function routeFetch(handler) {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const body = init.body ? JSON.parse(init.body) : undefined
      calls.push({ method: init.method ?? 'GET', url, body })
      return handler({ method: init.method ?? 'GET', url, body })
    }),
  )
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('utilitários de data', () => {
  it('converte entre datetime-local e ISO com fuso', () => {
    const iso = fromLocalInput('2026-09-15T09:30')
    expect(iso).toMatch(/Z$/)
    expect(toLocalInput(iso)).toBe('2026-09-15T09:30')
    expect(fromLocalInput('')).toBeNull()
    expect(toLocalInput(null)).toBe('')
  })

  it('atalhos: em 1h, amanhã 9h e próxima segunda 9h', () => {
    const base = new Date(2026, 8, 16, 14, 20) // quarta-feira
    const [oneHour, tomorrow, monday] = reminderPresets(base)

    expect(oneHour.at.getHours()).toBe(15)
    expect([tomorrow.at.getDate(), tomorrow.at.getHours()]).toEqual([17, 9])
    expect([monday.at.getDay(), monday.at.getDate(), monday.at.getHours()]).toEqual([1, 21, 9])
  })
})

describe('NoteCard', () => {
  it('destaca o termo buscado ignorando acento, sem HTML cru', () => {
    const wrapper = mount(NoteCard, { props: { note: note(1, { title: 'Integração <b>OpenAI</b>' }), highlight: 'integracao' } })

    expect(wrapper.find('mark.hit').text()).toBe('Integração')
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.find('.note__title').text()).toBe('Integração <b>OpenAI</b>')
  })

  it('mostra estado do lembrete e pede confirmação para excluir', async () => {
    const due = mount(NoteCard, { props: { note: note(1, { remind_at: NOW.toISOString(), reminder_due: true }) } })
    expect(due.find('.note__reminder').attributes('data-tone')).toBe('due')

    const button = due.find('.note__delete')
    await button.trigger('click')
    expect(due.emitted('delete')).toBeUndefined()
    expect(button.text()).toContain('Excluir?')
    await button.trigger('click')
    expect(due.emitted('delete')).toHaveLength(1)
  })

  it('lembrete em aberto tem Concluir; concluído não tem e diz que foi concluído', async () => {
    const due = mount(NoteCard, { props: { note: note(1, { remind_at: NOW.toISOString(), reminder_due: true }) } })
    await due.find('.note__complete').trigger('click')
    expect(due.emitted('complete')[0][0].id).toBe(1)

    const upcoming = mount(NoteCard, { props: { note: note(2, { remind_at: new Date(Date.now() + 3_600_000).toISOString() }) } })
    expect(upcoming.find('.note__complete').exists()).toBe(true)

    const done = mount(NoteCard, { props: { note: note(3, { remind_at: NOW.toISOString(), reminded_at: NOW.toISOString() }) } })
    expect(done.find('.note__complete').exists()).toBe(false)
    expect(done.find('.note__reminder').text()).toContain('Concluído')

    expect(mount(NoteCard, { props: { note: note(4) } }).find('.note__complete').exists()).toBe(false)
  })

  it('chips de tarefa e tag emitem eventos', async () => {
    const wrapper = mount(NoteCard, { props: { note: note(1, { tags: ['backend'], issues: [{ key: 'WAI-1', in_mirror: true }] }) } })

    await wrapper.find('.note__issue').trigger('click')
    await wrapper.find('.note__tag').trigger('click')

    expect(wrapper.emitted('open-issue')[0][0].key).toBe('WAI-1')
    expect(wrapper.emitted('select-tag')[0]).toEqual(['backend'])
  })
})

describe('NoteEditor', () => {
  it('cria com tags e chaves normalizadas e atalho de horário', async () => {
    routeFetch(({ method }) => (method === 'POST' ? json(201, note(9)) : json(200, {})))
    const store = useNotesStore()
    const wrapper = mount(NoteEditor, { attachTo: document.body })
    store.openEditor(null, { issue_keys: ['WAI-8295'] })
    await flushPromises()

    const dialog = document.body.querySelector('.editor')
    const setValue = async (selector, value) => {
      const el = dialog.querySelector(selector)
      el.value = value
      el.dispatchEvent(new Event('input'))
      await flushPromises()
    }
    await setValue('.editor__title', 'Integração OpenAI')
    await setValue('#note-tags', '#Backend, boas praticas')
    dialog.querySelector('#note-tags').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await setValue('#note-links', 'wai-9')
    dialog.querySelector('#note-links').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await flushPromises()
    dialog.querySelectorAll('.editor__preset')[1].click() // Amanhã 9h
    dialog.querySelector('[title="Rosa"]').click()
    await flushPromises()

    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }))
    await flushPromises()

    const post = calls.find((c) => c.method === 'POST')
    expect(post.url).toBe('/api/notes')
    expect(post.body).toMatchObject({ title: 'Integração OpenAI', color: 'pink', tags: ['backend', 'boas-praticas'], issue_keys: ['WAI-8295', 'WAI-9'] })
    expect(new Date(post.body.remind_at).getHours()).toBe(9)
    expect(store.editor.open).toBe(false)
    expect(store.revision).toBe(1)
    wrapper.unmount()
  })

  it('edita com PATCH, mostra erro da API e Esc fecha', async () => {
    routeFetch(() => json(422, { detail: 'Escreva um título ou um texto para o lembrete.' }))
    const store = useNotesStore()
    const wrapper = mount(NoteEditor, { attachTo: document.body })
    store.openEditor(note(3, { issues: [{ key: 'WAI-1' }] }))
    await flushPromises()

    document.body.querySelector('button[type="submit"]').click()
    await flushPromises()

    expect(calls[0]).toMatchObject({ method: 'PATCH', url: '/api/notes/3' })
    expect(calls[0].body.issue_keys).toEqual(['WAI-1'])
    expect(document.body.querySelector('.editor__error').textContent).toContain('Escreva um título')
    expect(store.editor.open).toBe(true)

    document.body.querySelector('.editor').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(store.editor.open).toBe(false)
    wrapper.unmount()
  })

  it('texto que não é chave nem item da lista é recusado no campo', async () => {
    const store = useNotesStore()
    const wrapper = mount(NoteEditor, { attachTo: document.body })
    store.openEditor()
    await flushPromises()

    const input = document.body.querySelector('#note-links')
    input.value = 'nao-e-chave'
    input.dispatchEvent(new Event('input'))
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await flushPromises()

    expect(document.body.querySelector('.links__error').textContent).toContain('Nada para vincular com "nao-e-chave"')
    expect(store.editor.draft.issue_keys).toEqual([])
    wrapper.unmount()
  })
})

describe('ReminderCenter', () => {
  it('mostra lembretes vencidos e resolve com concluir e adiar', async () => {
    let due = [note(1, { title: 'Revisar PR', remind_at: NOW.toISOString(), reminder_due: true }), note(2, { title: 'Daily', reminder_due: true, remind_at: NOW.toISOString() })]
    routeFetch(({ method, url }) => {
      if (url === '/api/notes/reminders/due') return json(200, due)
      if (method === 'POST' && url.endsWith('/reminder/ack')) {
        due = due.filter((n) => n.id !== 1)
        return json(200, note(1))
      }
      if (method === 'POST' && url.endsWith('/reminder/snooze')) {
        due = due.filter((n) => n.id !== 2)
        return json(200, note(2))
      }
      return json(200, {})
    })
    const wrapper = mount(ReminderCenter, { attachTo: document.body, props: { pollMs: 60_000 } })
    await flushPromises()

    let cards = document.body.querySelectorAll('.reminder')
    expect([...cards].map((c) => c.querySelector('.reminder__title').textContent)).toEqual(['Revisar PR', 'Daily'])

    ;[...cards[0].querySelectorAll('button')].find((b) => b.textContent === 'Concluir').click()
    await flushPromises()
    cards = document.body.querySelectorAll('.reminder')
    ;[...cards[0].querySelectorAll('button')].find((b) => b.textContent === 'Adiar 10 min').click()
    await flushPromises()

    expect(calls.find((c) => c.url === '/api/notes/1/reminder/ack')).toBeTruthy()
    expect(calls.find((c) => c.url === '/api/notes/2/reminder/snooze').body).toEqual({ minutes: 10 })
    expect(document.body.querySelectorAll('.reminder')).toHaveLength(0)
    wrapper.unmount()
  })
})

describe('NotesView', () => {
  const ITEMS = [note(1, { pinned: true, title: 'Fixado' }), note(2, { title: 'Integração', tags: ['backend'] }), note(3, { title: 'Outra' })]

  async function mountView(query = '') {
    routeFetch(({ url }) => {
      if (url.startsWith('/api/notes/tags')) return json(200, [{ tag: 'backend', count: 1 }])
      if (url.startsWith('/api/notes?')) return json(200, { items: ITEMS, total: 3 })
      return json(200, {})
    })
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push(`/lembretes${query}`)
    await router.isReady()
    const wrapper = mount(NotesView, { global: { plugins: [router], stubs: { IssueDrawer: true } } })
    await flushPromises()
    return { wrapper, router }
  }

  it('separa fixados, lista tags e filtra pela URL', async () => {
    const { wrapper, router } = await mountView('?filtro=lembrete&tag=backend')

    expect(wrapper.findAll('.notes__section').map((s) => s.text())).toEqual(['Fixados', 'Outros'])
    expect(wrapper.find('.notes__filter--on').text()).toBe('Com lembrete')
    expect(wrapper.find('.notes__tag--on').text()).toContain('#backend')
    const listCall = calls.find((c) => c.url.startsWith('/api/notes?'))
    expect(listCall.url).toContain('tag=backend')
    expect(listCall.url).toContain('due=upcoming')

    await wrapper.findAll('.notes__filter')[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.filtro).toBeUndefined()
  })

  it('busca com debounce vai para a URL e para a API', async () => {
    vi.useFakeTimers()
    const { wrapper, router } = await mountView()

    await wrapper.find('.notes__search input').setValue('retry')
    vi.advanceTimersByTime(300)
    vi.useRealTimers()
    await flushPromises()

    expect(router.currentRoute.value.query.q).toBe('retry')
    expect(calls.some((c) => c.url.includes('q=retry'))).toBe(true)
  })

  it('concluir na tela chama o mesmo endpoint da notificação', async () => {
    ITEMS[1].remind_at = NOW.toISOString()
    ITEMS[1].reminder_due = true
    const { wrapper } = await mountView()

    await wrapper.find('.note__complete').trigger('click')
    await flushPromises()

    expect(calls.find((c) => c.method === 'POST')).toMatchObject({ url: '/api/notes/2/reminder/ack' })
    ITEMS[1].remind_at = null
    ITEMS[1].reminder_due = false
  })

  it('tarefa do espelho abre o painel pela URL', async () => {
    ITEMS[2].issues = [{ key: 'WAI-8295', in_mirror: true }]
    const { wrapper, router } = await mountView()

    await wrapper.find('.note__issue').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.tarefa).toBe('WAI-8295')
  })
})

describe('IssueNotesTab', () => {
  it('lista lembretes da tarefa e cria já vinculado', async () => {
    routeFetch(() => json(200, { items: [note(5, { issues: [{ key: 'WAI-124', in_mirror: true }] })], total: 1 }))
    const store = useNotesStore()
    const wrapper = mount(IssueNotesTab, { props: { issueKey: 'WAI-124' } })
    await flushPromises()

    expect(calls[0].url).toBe('/api/notes?issue_key=WAI-124&include_archived=true&limit=100')
    expect(wrapper.findAll('.note')).toHaveLength(1)
    expect(wrapper.emitted('count')[0]).toEqual([1])

    await wrapper.find('.issue-notes__new').trigger('click')
    expect(store.editor.open).toBe(true)
    expect(store.editor.draft.issue_keys).toEqual(['WAI-124'])
  })
})

describe('NoteEditor: vínculos e menções', () => {
  function openEditor(note = null) {
    routeFetch(() => json(200, []))
    const store = useNotesStore()
    const wrapper = mount(NoteEditor, { attachTo: document.body })
    store.openEditor(note)
    return { store, wrapper }
  }

  it('Tags e Vínculos ficam em linhas próprias, com um campo só para tarefas e repositórios', async () => {
    const { wrapper } = openEditor()
    await flushPromises()

    const labels = [...document.body.querySelectorAll('.editor > .field > .field__label')].map((l) => l.textContent)
    expect(labels).toEqual(['Tags', 'Vínculos', 'Lembrar em'])
    expect(document.body.querySelector('#note-issues')).toBeNull()
    expect(document.body.querySelector('#note-repos')).toBeNull()
    wrapper.unmount()
  })

  it('ao sair da descrição, o que foi citado e apagado do texto sai dos vínculos e das tags', async () => {
    const { store, wrapper } = openEditor(
      note(7, {
        body: 'Subir @organia-configs com #deploy e ver @WAI-8458',
        tags: ['deploy', 'manual'],
        repos: ['organia-configs', 'monitoria'],
        issues: [{ key: 'WAI-8458' }, { key: 'WAI-1' }],
      }),
    )
    await flushPromises()

    const textarea = document.body.querySelector('.mention__field')
    textarea.value = 'Ver @WAI-8458'
    textarea.dispatchEvent(new Event('input'))
    textarea.dispatchEvent(new Event('blur'))
    await flushPromises()

    const draft = store.editor.draft
    // Citados e apagados saem; escolhidos nos campos (monitoria, WAI-1, manual) ficam.
    expect(draft.repos).toEqual(['monitoria'])
    expect(draft.tags).toEqual(['manual'])
    expect(draft.issue_keys).toEqual(['WAI-8458', 'WAI-1'])
    wrapper.unmount()
  })

  it('menção pintada no texto só quando é vínculo, com a cor do tipo', async () => {
    const { wrapper } = openEditor(note(8, { body: 'Ver @WAI-8458 e @monitoria e @outro #deploy', tags: ['deploy'], repos: ['monitoria'], issues: [{ key: 'WAI-8458' }] }))
    await flushPromises()

    const marks = [...document.body.querySelectorAll('.mention__mark')].map((m) => [m.dataset.kind, m.textContent])
    expect(marks).toEqual([['issue', '@WAI-8458'], ['repo', '@monitoria'], ['tag', '#deploy']])
    wrapper.unmount()
  })
})

describe('menções no texto (utilitário)', () => {
  it('separa tag, tarefa e repositório e ignora pontuação e e-mail', () => {
    const found = mentionsIn('Ver @wai-12, @Organia-Configs. #Boas-Praticas e dev@weon')

    expect([...found.issue]).toEqual(['WAI-12'])
    expect([...found.repo]).toEqual(['organia-configs'])
    expect([...found.tag]).toEqual(['boas-praticas'])
  })

  it('partes preservam o texto inteiro', () => {
    const text = 'a @WAI-1 b'
    const parts = mentionParts(text, { issue: ['WAI-1'] })

    expect(parts.map((p) => p.text).join('')).toBe(text)
    expect(parts.find((p) => p.kind)).toEqual({ text: '@WAI-1', kind: 'issue' })
  })
})

describe('LinksField', () => {
  const ISSUES = [
    { key: 'WAI-8458', summary: 'Oferecer qualificações só nos canais', issue_type: 'Tarefa', status: 'Em Desenvolvimento', status_category: 'indeterminate', assignee_name: 'Matheus Bacca', is_mine: true },
    { key: 'WAI-8433', summary: 'CRUD de qualificações', issue_type: 'Tarefa', status: 'Concluído', status_category: 'done', assignee_name: 'Outro', is_mine: false },
  ]

  function mountField({ issues = [], repos = [], availableRepos = [] } = {}) {
    routeFetch(() => json(200, ISSUES))
    const updates = { issues: [], repos: [] }
    const wrapper = mount(LinksField, {
      props: {
        issues,
        repos,
        availableRepos,
        'onUpdate:issues': (v) => updates.issues.push(v),
        'onUpdate:repos': (v) => updates.repos.push(v),
      },
      attachTo: document.body,
    })
    return { wrapper, updates }
  }

  it('só busca ao ganhar foco; lista repositórios acompanhados e tarefas', async () => {
    const { wrapper } = mountField({ availableRepos: ['monitoria', 'organia-configs'] })
    await flushPromises()
    expect(calls).toEqual([])

    await wrapper.find('input').trigger('focus')
    await flushPromises()

    expect(calls[0].url).toBe('/api/issues?limit=30')
    expect(wrapper.findAll('.links__item').map((li) => `${li.attributes('data-kind')}:${li.attributes('data-key')}`)).toEqual([
      'repo:monitoria',
      'repo:organia-configs',
      'issue:WAI-8458',
      'issue:WAI-8433',
    ])
    expect(wrapper.emitted('activate')).toHaveLength(1)
    wrapper.unmount()
  })

  it('digitar filtra os repositórios na hora e busca as tarefas no back, com debounce', async () => {
    const { wrapper } = mountField({ availableRepos: ['monitoria', 'organia-configs'] })
    await wrapper.find('input').trigger('focus')
    await flushPromises()
    vi.useFakeTimers()

    await wrapper.find('input').setValue('organia')
    expect(wrapper.findAll('.links__item[data-kind="repo"]').map((li) => li.attributes('data-key'))).toEqual(['organia-configs'])
    vi.advanceTimersByTime(250)
    vi.useRealTimers()
    await flushPromises()

    expect(calls.at(-1).url).toBe('/api/issues?q=organia&limit=30')
    wrapper.unmount()
  })

  it('tarefas e repositórios viram chips com cor do tipo e marcam/desmarcam pela lista', async () => {
    const { wrapper, updates } = mountField({ issues: ['WAI-1'], repos: ['monitoria'], availableRepos: ['monitoria', 'organia-configs'] })
    expect(wrapper.findAll('.links__chip').map((c) => `${c.attributes('data-kind')}:${c.text()}`)).toEqual(['issue:WAI-1', 'repo:monitoria'])

    await wrapper.find('input').trigger('focus')
    await flushPromises()
    const items = wrapper.findAll('.links__item')
    await items[0].trigger('click') // monitoria já vinculado: desmarca
    await items[1].trigger('click') // organia-configs
    await items[2].trigger('click') // WAI-8458

    expect(updates.repos).toEqual([[], ['monitoria', 'organia-configs']])
    expect(updates.issues.at(-1)).toEqual(['WAI-1', 'WAI-8458'])
    wrapper.unmount()
  })

  it('Enter marca a ativa sem submeter; chave inteira digitada vale ela mesma', async () => {
    const { wrapper, updates } = mountField()
    await wrapper.find('input').trigger('focus')
    await flushPromises()

    const enter = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true })
    wrapper.find('input').element.dispatchEvent(enter)
    expect(enter.defaultPrevented).toBe(true)
    expect(updates.issues.at(-1)).toEqual(['WAI-8458'])

    await wrapper.find('input').setValue('wai-9 WAI-10')
    await wrapper.find('input').trigger('keydown', { key: 'Enter' })
    expect(updates.issues.at(-1)).toEqual(['WAI-9', 'WAI-10'])
    wrapper.unmount()
  })

  it('Backspace no campo vazio desvincula o último chip; o X desvincula o escolhido', async () => {
    const { wrapper, updates } = mountField({ issues: ['WAI-1', 'WAI-2'], repos: ['monitoria'] })

    await wrapper.find('input').trigger('keydown', { key: 'Backspace' })
    expect(updates.repos.at(-1)).toEqual([])
    await wrapper.find('.links__chip[data-kind="issue"] button').trigger('click')
    expect(updates.issues.at(-1)).toEqual(['WAI-2'])
    wrapper.unmount()
  })

  it('primeiro Esc fecha só a lista', async () => {
    const { wrapper } = mountField()
    await wrapper.find('input').trigger('focus')
    await flushPromises()

    const bubbled = vi.fn()
    document.body.addEventListener('keydown', bubbled)
    wrapper.find('input').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(wrapper.find('.links__list').exists()).toBe(false)
    expect(bubbled).not.toHaveBeenCalled()
    document.body.removeEventListener('keydown', bubbled)
    wrapper.unmount()
  })
})

describe('MentionTextarea', () => {
  const MINE = [{ key: 'WAI-8458', summary: 'Oferecer qualificações só nos canais', issue_type: 'Tarefa', status: 'Em Desenvolvimento', status_category: 'indeterminate', assignee_name: 'Matheus Bacca', is_mine: true }]

  function mountText(props = {}) {
    routeFetch(() => json(200, MINE))
    const events = { tag: [], repo: [], issue: [] }
    const wrapper = mount(MentionTextarea, {
      props: {
        modelValue: '',
        tags: ['backend', 'boas-praticas'],
        repos: ['organia-configs', 'monitoria'],
        'onUpdate:modelValue': (v) => wrapper.setProps({ modelValue: v }),
        'onAdd-tag': (v) => events.tag.push(v),
        'onAdd-repo': (v) => events.repo.push(v),
        'onAdd-issue': (v) => events.issue.push(v),
        ...props,
      },
      attachTo: document.body,
    })
    return { wrapper, events }
  }

  /** Simula digitar no fim do texto, um evento de input por caractere. */
  async function type(wrapper, text) {
    const el = wrapper.find('textarea').element
    for (const char of text) {
      el.value += char
      el.setSelectionRange(el.value.length, el.value.length)
      el.dispatchEvent(new InputEvent('input', { data: char, inputType: 'insertText' }))
      await flushPromises()
    }
  }

  const enter = (wrapper) => {
    const event = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true })
    wrapper.find('textarea').element.dispatchEvent(event)
    return event
  }

  it('#nome composto + Enter vira tag normalizada no texto e no campo', async () => {
    const { wrapper, events } = mountText()

    await type(wrapper, 'Revisar #boas praticas novas')
    expect(wrapper.find('.mention__item').text()).toContain('#boas-praticas-novas')
    const event = enter(wrapper)
    await flushPromises()

    expect(event.defaultPrevented).toBe(true)
    expect(events.tag).toEqual(['boas-praticas-novas'])
    expect(wrapper.props('modelValue')).toBe('Revisar #boas-praticas-novas ')
    expect(wrapper.find('.mention__list').exists()).toBe(false)
    wrapper.unmount()
  })

  it('sem Enter o # continua só texto', async () => {
    const { wrapper, events } = mountText()

    await type(wrapper, '#urgente')
    wrapper.find('textarea').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()

    expect(events.tag).toEqual([])
    expect(wrapper.props('modelValue')).toBe('#urgente')
    wrapper.unmount()
  })

  it('@ sugere repositório acompanhado e vincula', async () => {
    const { wrapper, events } = mountText()

    await type(wrapper, 'Subir @organia')
    const items = wrapper.findAll('.mention__item')
    expect(items[0].attributes('data-kind')).toBe('repo')
    enter(wrapper)
    await flushPromises()

    expect(events.repo).toEqual(['organia-configs'])
    expect(wrapper.props('modelValue')).toBe('Subir @organia-configs ')
    wrapper.unmount()
  })

  it('@ busca só as tarefas do dev e vincula a escolhida', async () => {
    const { wrapper, events } = mountText()

    await type(wrapper, '@qualif')
    await new Promise((r) => setTimeout(r, 200))
    await flushPromises()

    expect(calls.at(-1).url).toBe('/api/issues?q=qualif&mine=true&limit=6')
    const issue = wrapper.find('.mention__item[data-kind="issue"]')
    expect(issue.text()).toContain('@WAI-8458')
    await issue.trigger('click')
    await flushPromises()

    expect(events.issue).toEqual(['WAI-8458'])
    expect(wrapper.props('modelValue')).toBe('@WAI-8458 ')
    wrapper.unmount()
  })

  it('@ no meio de uma palavra (e-mail) não abre sugestão', async () => {
    const { wrapper } = mountText()

    await type(wrapper, 'dev@weon')

    expect(wrapper.find('.mention__list').exists()).toBe(false)
    wrapper.unmount()
  })
})
