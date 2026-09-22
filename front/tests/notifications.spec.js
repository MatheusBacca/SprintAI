import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import NotificationBell from '@/components/shell/NotificationBell.vue'
import NotificationPins from '@/components/shell/NotificationPins.vue'
import { useNotesStore } from '@/stores/notes'
import { useNotificationsStore } from '@/stores/notifications'

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
    remind_at: NOW.toISOString(),
    reminded_at: null,
    reminder_due: true,
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
let due

function routeFetch() {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const body = init.body ? JSON.parse(init.body) : undefined
      calls.push({ method: init.method ?? 'GET', url, body })
      if (url === '/api/notes/reminders/due') return json(200, due)
      if (url.endsWith('/reminder/ack')) {
        due = due.filter((n) => `/api/notes/${n.id}/reminder/ack` !== url)
        return json(200, note(1))
      }
      if (url.endsWith('/reminder/snooze')) {
        due = due.filter((n) => `/api/notes/${n.id}/reminder/snooze` !== url)
        return json(200, note(1))
      }
      return json(200, {})
    }),
  )
}

const bell = () => document.body.querySelector('.notif__bell')
const badge = () => document.body.querySelector('.notif__badge')
const items = () => [...document.body.querySelectorAll('.notif__item')]
const click = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent.trim() === text).click()

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  due = [note(1, { title: 'Revisar PR' }), note(2, { title: 'Daily' })]
  routeFetch()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

async function mountBell() {
  const store = useNotificationsStore()
  const wrapper = mount(NotificationBell, { attachTo: document.body })
  await store.poll()
  await flushPromises()
  return { store, wrapper }
}

describe('sino de notificações', () => {
  it('o selo conta o que ainda não foi visto e zera ao abrir o painel', async () => {
    const { store, wrapper } = await mountBell()

    expect(badge().textContent).toBe('2')
    // A lista só existe com o painel aberto: nada sobreposto na tela.
    expect(items()).toHaveLength(0)

    bell().click()
    await flushPromises()

    expect(items().map((li) => li.querySelector('.notif__title').textContent)).toEqual(['Revisar PR', 'Daily'])
    expect(badge()).toBeNull()
    expect(store.unseenCount).toBe(0)
    wrapper.unmount()
  })

  it('lembrete que chega com o painel fechado volta a somar no selo', async () => {
    const { store, wrapper } = await mountBell()
    store.openPanel()
    store.closePanel()
    await flushPromises()
    expect(badge()).toBeNull()

    due = [...due, note(3, { title: 'Deploy' })]
    await store.poll()
    await flushPromises()

    expect(badge().textContent).toBe('1')
    wrapper.unmount()
  })

  it('concluir e adiar chamam os mesmos endpoints e somem da lista', async () => {
    const { wrapper } = await mountBell()
    bell().click()
    await flushPromises()

    click(items()[0], 'Concluir')
    await flushPromises()
    click(items()[0], 'Adiar 10 min')
    await flushPromises()

    expect(calls.find((c) => c.url === '/api/notes/1/reminder/ack')).toBeTruthy()
    expect(calls.find((c) => c.url === '/api/notes/2/reminder/snooze').body).toEqual({ minutes: 10 })
    expect(items()).toHaveLength(0)
    expect(document.body.querySelector('.notif__empty').textContent).toContain('Nenhuma notificação')
    wrapper.unmount()
  })

  it('"Abrir" leva ao editor do lembrete e fecha o painel', async () => {
    const notes = useNotesStore()
    const { store, wrapper } = await mountBell()
    store.openPanel()
    await flushPromises()

    click(items()[0], 'Abrir')
    await flushPromises()

    expect(notes.editor.open).toBe(true)
    expect(notes.editor.draft.id).toBe(1)
    expect(store.open).toBe(false)
    wrapper.unmount()
  })

  it('clique fora e Esc fecham o painel', async () => {
    const { store, wrapper } = await mountBell()
    store.openPanel()
    await flushPromises()

    // jsdom não tem PointerEvent; o listener só olha o alvo do evento.
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(store.open).toBe(false)

    store.openPanel()
    await flushPromises()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(store.open).toBe(false)
    wrapper.unmount()
  })
})

describe('notificações fixadas no header', () => {
  async function mountBoth() {
    const store = useNotificationsStore()
    const pins = mount(NotificationPins, { attachTo: document.body })
    const panel = mount(NotificationBell, { attachTo: document.body })
    await store.poll()
    await flushPromises()
    return { store, unmount: () => [pins, panel].forEach((w) => w.unmount()) }
  }

  it('o pin do painel sobe só o título para o header e o clique abre a modal do lembrete', async () => {
    const notes = useNotesStore()
    const { store, unmount } = await mountBoth()
    expect(document.body.querySelector('.pins')).toBeNull()

    store.openPanel()
    await flushPromises()
    items()[1].querySelector('.notif__pin').click()
    await flushPromises()

    const chips = [...document.body.querySelectorAll('.pins__open')]
    expect(chips.map((c) => c.textContent.trim())).toEqual(['Daily'])
    // Só o título: horário e ações ficam na modal e no painel.
    expect(document.body.querySelector('.pins__item').textContent).not.toContain('Concluir')

    store.closePanel()
    await flushPromises()
    chips[0].click()
    await flushPromises()

    expect(notes.editor.open).toBe(true)
    expect(notes.editor.draft.id).toBe(2)
    expect(store.open).toBe(false)
    unmount()
  })

  it('o que foi fixado atravessa o recarregar da página; concluir solta o pin', async () => {
    const { store, unmount } = await mountBoth()
    store.openPanel()
    await flushPromises()
    items()[0].querySelector('.notif__pin').click()
    await flushPromises()
    expect(JSON.parse(localStorage.getItem('sprintai.notifications.pinned'))).toEqual([1])

    // Outra sessão do app lendo o mesmo localStorage.
    setActivePinia(createPinia())
    const recarregado = useNotificationsStore()
    expect(recarregado.pinnedIds).toEqual([1])

    await recarregado.poll()
    expect(recarregado.pinned.map((n) => n.id)).toEqual([1])
    await recarregado.acknowledge(1)

    expect(recarregado.pinnedIds).toEqual([])
    expect(JSON.parse(localStorage.getItem('sprintai.notifications.pinned'))).toEqual([])
    unmount()
  })

  it('desafixar pelo X do chip tira do header sem mexer no lembrete', async () => {
    const { store, unmount } = await mountBoth()
    store.togglePin(1)
    await flushPromises()

    document.body.querySelector('.pins__off').click()
    await flushPromises()

    expect(document.body.querySelector('.pins')).toBeNull()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    unmount()
  })
})
