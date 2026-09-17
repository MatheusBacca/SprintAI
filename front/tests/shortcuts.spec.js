import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import ReminderPalette from '@/components/notes/ReminderPalette.vue'
import ShortcutsPanel from '@/components/settings/ShortcutsPanel.vue'
import GlobalShortcuts from '@/components/shell/GlobalShortcuts.vue'
import { routes } from '@/router/routes'
import { useNotesStore } from '@/stores/notes'
import { useScreenContextStore } from '@/stores/screenContext'
import { useShortcutsStore } from '@/stores/shortcuts'
import { highlightParts, snippetAround } from '@/utils/highlight'
import {
  DEFAULT_BINDINGS,
  anyWordQuery,
  comboFromEvent,
  conflictingAction,
  issueKeysIn,
  readSelection,
  searchTermFrom,
  validateCombo,
} from '@/utils/shortcuts'

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
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
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

const key = (code, mods = {}) => new KeyboardEvent('keydown', { code, key: code.replace(/^Key/, '').toLowerCase(), bubbles: true, cancelable: true, ...mods })

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  vi.unstubAllGlobals()
  document.getSelection()?.removeAllRanges()
  document.body.innerHTML = ''
})

describe('regras de atalho', () => {
  it('lê a tecla física, independente de layout e do Shift', () => {
    expect(comboFromEvent(key('KeyL', { ctrlKey: true, shiftKey: true }))).toBe('Ctrl+Shift+L')
    expect(comboFromEvent(key('Digit7', { altKey: true }))).toBe('Alt+7')
    expect(comboFromEvent(key('F2'))).toBe('F2')
    expect(comboFromEvent(new KeyboardEvent('keydown', { code: 'ShiftLeft', key: 'Shift', shiftKey: true }))).toBeNull()
    expect(comboFromEvent(key('KeyL', { metaKey: true }))).toBeNull()
    expect(comboFromEvent(key('Enter', { ctrlKey: true }))).toBeNull()
    // sem `code` (teclado virtual/automação): cai para `key`
    expect(comboFromEvent(new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, shiftKey: true }))).toBe('Ctrl+Shift+L')
  })

  it.each([
    ['Ctrl+Shift+L', null],
    ['Alt+N', null],
    ['Alt+Shift+Space', null],
    ['F2', null],
    ['Ctrl+K', null],
    ['Ctrl+Alt+N', 'AltGr'],
    ['Ctrl+Shift+N', 'reservado'],
    ['Alt+F4', 'reservado'],
    ['F5', 'reservado'],
    ['Shift+L', 'Ctrl ou Alt'],
    ['Ctrl+C', 'edição'],
    ['Ctrl+Shift+Enter', 'tecla'],
  ])('%s → %s (mesma tabela do back)', (combo, fragment) => {
    const result = validateCombo(combo)
    if (fragment === null) expect(result).toBeNull()
    else expect(result).toContain(fragment)
  })

  it('padrões são válidos e não conflitam', () => {
    expect(Object.values(DEFAULT_BINDINGS).map(validateCombo)).toEqual([null, null, null])
    expect(conflictingAction(DEFAULT_BINDINGS, 'Ctrl+Shift+L', 'new_reminder').id).toBe('open_reminders')
    expect(conflictingAction(DEFAULT_BINDINGS, 'Ctrl+Shift+L', 'open_reminders')).toBeNull()
  })

  it('seleção vem do campo focado ou da página, nunca de senha', () => {
    const area = document.createElement('textarea')
    area.value = 'retry exponencial no client'
    document.body.append(area)
    area.focus()
    area.setSelectionRange(6, 17)
    expect(readSelection()).toBe('exponencial')

    const password = document.createElement('input')
    password.type = 'password'
    password.value = 'segredo'
    document.body.append(password)
    password.focus()
    password.setSelectionRange(0, 7)
    expect(readSelection()).toBe('')

    password.blur()
    const p = document.createElement('p')
    p.textContent = 'Descrição da WAI-8295'
    document.body.append(p)
    const range = document.createRange()
    range.selectNodeContents(p)
    document.getSelection().addRange(range)
    expect(readSelection()).toBe('Descrição da WAI-8295')
  })

  it('termo, chaves e "qualquer palavra"', () => {
    expect(searchTermFrom('  linha 1\n\n linha 2 ')).toBe('linha 1 linha 2')
    expect(issueKeysIn('ver WAI-8295 e WAI-12, WAI-8295')).toEqual(['WAI-8295', 'WAI-12'])
    expect(anyWordQuery('retry "exponencial" -client')).toBe('retry or exponencial or client')
    expect(anyWordQuery('retry')).toBeNull()
  })

  it('destaque e trecho ignoram acento', () => {
    expect(highlightParts('Integração OpenAI', 'integracao')).toEqual([
      { text: 'Integração', hit: true },
      { text: ' OpenAI', hit: false },
    ])
    const long = `${'a'.repeat(200)} exponencial ${'b'.repeat(200)}`
    const snippet = snippetAround(long, 'exponencial', 20)
    expect(snippet.startsWith('…')).toBe(true)
    expect(snippet).toContain('exponencial')
    expect(snippet.length).toBeLessThan(70)
  })
})

describe('GlobalShortcuts', () => {
  async function mountShortcuts(bindings = DEFAULT_BINDINGS) {
    routeFetch(({ url }) => (url.includes('/preferences/shortcuts') ? json(200, { bindings, defaults: DEFAULT_BINDINGS }) : json(200, {})))
    const wrapper = mount(GlobalShortcuts, { attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  it('abre a modal com o texto selecionado; sem seleção, com a tarefa em foco', async () => {
    const wrapper = await mountShortcuts()
    const notes = useNotesStore()
    const screen = useScreenContextStore()

    const p = document.createElement('p')
    p.textContent = '  retry\n exponencial '
    document.body.append(p)
    const range = document.createRange()
    range.selectNodeContents(p)
    document.getSelection().addRange(range)

    const event = key('KeyL', { ctrlKey: true, shiftKey: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(notes.palette).toEqual({ open: true, query: 'retry exponencial', source: 'selection' })

    window.dispatchEvent(key('KeyL', { ctrlKey: true, shiftKey: true })) // mesmo atalho fecha
    expect(notes.palette.open).toBe(false)

    document.getSelection().removeAllRanges()
    screen.focusIssue('WAI-8295')
    window.dispatchEvent(key('KeyL', { ctrlKey: true, shiftKey: true }))
    expect(notes.palette).toEqual({ open: true, query: 'WAI-8295', source: 'issue' })
    wrapper.unmount()
  })

  it('novo lembrete leva a seleção e as tarefas citadas', async () => {
    const wrapper = await mountShortcuts()
    const notes = useNotesStore()
    useScreenContextStore().focusIssue('WAI-1')

    const area = document.createElement('textarea')
    area.value = 'Achado: WAI-8295 depende do retry'
    document.body.append(area)
    area.focus()
    area.select()

    window.dispatchEvent(key('KeyA', { ctrlKey: true, shiftKey: true }))
    expect(notes.editor.open).toBe(true)
    expect(notes.editor.draft.body).toBe('Achado: WAI-8295 depende do retry')
    expect(notes.editor.draft.issue_keys).toEqual(['WAI-8295', 'WAI-1'])
    wrapper.unmount()
  })

  it('usa o atalho salvo, ignora o antigo e fica suspenso enquanto grava', async () => {
    const wrapper = await mountShortcuts({ open_reminders: 'Alt+J', new_reminder: null })
    const notes = useNotesStore()
    const shortcuts = useShortcutsStore()

    const old = key('KeyL', { ctrlKey: true, shiftKey: true })
    window.dispatchEvent(old)
    expect(old.defaultPrevented).toBe(false)
    expect(notes.palette.open).toBe(false)

    shortcuts.recording = true
    window.dispatchEvent(key('KeyJ', { altKey: true }))
    expect(notes.palette.open).toBe(false)

    shortcuts.recording = false
    window.dispatchEvent(key('KeyJ', { altKey: true }))
    expect(notes.palette.open).toBe(true)
    wrapper.unmount()
  })

  it('com o editor aberto não empilha modal, mas segura o atalho do navegador', async () => {
    const wrapper = await mountShortcuts()
    const notes = useNotesStore()
    notes.openEditor()

    const event = key('KeyL', { ctrlKey: true, shiftKey: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(notes.palette.open).toBe(false)
    wrapper.unmount()
  })
})

describe('ReminderPalette', () => {
  async function mountPalette(handler) {
    routeFetch(handler)
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/sprints')
    await router.isReady()
    const wrapper = mount(ReminderPalette, { props: { debounceMs: 0 }, attachTo: document.body, global: { plugins: [router] } })
    return { wrapper, router }
  }

  const dialog = () => document.body.querySelector('.palette')
  const press = (keyName, mods = {}) =>
    document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: keyName, bubbles: true, cancelable: true, ...mods }))

  it('busca pelo termo inicial, destaca e abre a nota escolhida pelo teclado', async () => {
    const { wrapper } = await mountPalette(() =>
      json(200, { items: [note(1, { title: 'Retry no client' }), note(2, { title: 'Outro', body: 'usar retry exponencial', issues: [{ key: 'WAI-1' }] })], total: 2 }),
    )
    const notes = useNotesStore()
    notes.openPalette('retry', 'selection')
    await flushPromises()

    expect(calls[0].url).toContain('q=retry')
    expect(dialog().querySelector('.palette__source').textContent).toContain('Da seleção')
    expect(document.activeElement).toBe(dialog().querySelector('input'))
    expect(dialog().querySelector('.palette__item mark.hit').textContent).toBe('Retry')

    press('ArrowDown')
    await flushPromises()
    expect(dialog().querySelectorAll('.palette__item')[1].getAttribute('aria-selected')).toBe('true')

    press('Enter')
    await flushPromises()
    expect(notes.palette.open).toBe(false)
    expect(notes.editor.open).toBe(true)
    expect(notes.editor.draft.id).toBe(2)
    wrapper.unmount()
  })

  it('sem resultado com todas as palavras, tenta qualquer uma', async () => {
    const { wrapper } = await mountPalette(({ url }) =>
      url.includes('+or+') ? json(200, { items: [note(3)], total: 1 }) : json(200, { items: [], total: 0 }),
    )
    useNotesStore().openPalette('retry exponencial do client', 'selection')
    await flushPromises()

    expect(calls).toHaveLength(2)
    expect(decodeURIComponent(calls[1].url)).toContain('q=retry+or+exponencial+or+do+or+client')
    expect(dialog().querySelector('.palette__hint')).not.toBeNull()
    expect(dialog().querySelectorAll('.palette__item')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Ctrl+Enter cria lembrete com o termo e a tarefa em foco; Esc fecha', async () => {
    const { wrapper } = await mountPalette(() => json(200, { items: [], total: 0 }))
    const notes = useNotesStore()
    useScreenContextStore().focusIssue('WAI-8295')

    notes.openPalette('checar WAI-12 antes do deploy')
    await flushPromises()
    expect(dialog().querySelector('.palette__empty').textContent).toContain('checar WAI-12')

    press('Enter', { ctrlKey: true })
    await flushPromises()
    expect(notes.editor.draft.body).toBe('checar WAI-12 antes do deploy')
    expect(notes.editor.draft.issue_keys).toEqual(['WAI-12', 'WAI-8295'])

    notes.closeEditor()
    notes.openPalette('')
    await flushPromises()
    press('Escape')
    await flushPromises()
    expect(notes.palette.open).toBe(false)
    expect(document.body.querySelector('.palette')).toBeNull()
    wrapper.unmount()
  })

  it('"Ver no mural" leva a busca para /lembretes', async () => {
    const { wrapper, router } = await mountPalette(() => json(200, { items: [note(1)], total: 30 }))
    useNotesStore().openPalette('retry')
    await flushPromises()

    expect(dialog().querySelector('.palette__more').textContent).toBe('+29')
    dialog().querySelector('.palette__footer .btn--secondary').click()
    await flushPromises()
    // a rota carrega a view sob demanda
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/lembretes?q=retry'))
    wrapper.unmount()
  })
})

describe('ShortcutsPanel', () => {
  async function mountPanel() {
    routeFetch(({ method, body }) =>
      method === 'PUT'
        ? json(200, { bindings: body.bindings, defaults: DEFAULT_BINDINGS })
        : json(200, { bindings: DEFAULT_BINDINGS, defaults: DEFAULT_BINDINGS }),
    )
    const wrapper = mount(ShortcutsPanel, { attachTo: document.body })
    await flushPromises()
    return wrapper
  }

  const row = (wrapper, action) => wrapper.find(`[data-action="${action}"]`)

  it('grava um atalho novo, recusa reservado e conflito, e salva', async () => {
    const wrapper = await mountPanel()
    const shortcuts = useShortcutsStore()
    const recorder = row(wrapper, 'open_reminders').find('.shortcuts__recorder')

    await recorder.trigger('click')
    expect(shortcuts.recording).toBe(true)

    await recorder.trigger('keydown', { code: 'KeyN', key: 'N', ctrlKey: true, shiftKey: true })
    expect(row(wrapper, 'open_reminders').find('.shortcuts__error').text()).toContain('reservado')

    await recorder.trigger('keydown', { code: 'KeyA', key: 'A', ctrlKey: true, shiftKey: true })
    expect(row(wrapper, 'open_reminders').find('.shortcuts__error').text()).toContain('Novo lembrete com a seleção')

    await recorder.trigger('keydown', { code: 'KeyJ', key: 'j', altKey: true })
    expect(shortcuts.recording).toBe(false)
    expect(row(wrapper, 'open_reminders').findAll('kbd').map((k) => k.text())).toEqual(['Alt', 'J'])

    await row(wrapper, 'new_reminder').findAll('button').find((b) => b.text() === 'Desativar').trigger('click')
    expect(row(wrapper, 'new_reminder').text()).toContain('Desativado')

    await wrapper.findAll('.shortcuts__footer button').at(-1).trigger('click')
    await flushPromises()
    const put = calls.find((c) => c.method === 'PUT')
    expect(put.body).toEqual({ bindings: { open_reminders: 'Alt+J', new_reminder: null, global_search: 'Ctrl+K' } })
    expect(shortcuts.bindings.open_reminders).toBe('Alt+J')
    expect(wrapper.find('.shortcuts__feedback').text()).toContain('salvos')
    wrapper.unmount()
  })

  it('Esc cancela a gravação sem mudar o atalho', async () => {
    const wrapper = await mountPanel()
    const recorder = row(wrapper, 'open_reminders').find('.shortcuts__recorder')
    await recorder.trigger('click')
    await recorder.trigger('keydown', { key: 'Escape', code: 'Escape' })

    expect(useShortcutsStore().recording).toBe(false)
    expect(recorder.findAll('kbd').map((k) => k.text())).toEqual(['Ctrl', 'Shift', 'L'])
    expect(wrapper.findAll('.shortcuts__footer button').at(-1).attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
