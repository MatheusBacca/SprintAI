import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import NotificationBell from '@/components/shell/NotificationBell.vue'
import NotificationPins from '@/components/shell/NotificationPins.vue'
import { routes } from '@/router/routes'
import { useNotesStore } from '@/stores/notes'
import { useNotificationsStore } from '@/stores/notifications'
import { useUiStore } from '@/stores/ui'

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

function update(key, extra = {}) {
  return {
    key,
    summary: `Resumo ${key}`,
    status: 'DISPONIVEL PARA REVIEW',
    status_category: 'new',
    story_points: 5,
    url: `https://weon.atlassian.net/browse/${key}`,
    kind: 'comment',
    source: 'jira',
    title: 'Achei um caso',
    actor_name: 'Rafael',
    occurred_at: NOW.toISOString(),
    event_count: 1,
    sprint_id: 3995,
    sprint_name: 'Sprint 73 - Growth',
    ...extra,
  }
}

function json(status, body) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }), json: async () => body, text: async () => '' }
}

let calls
let due
let updates

function routeFetch() {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const body = init.body ? JSON.parse(init.body) : undefined
      calls.push({ method: init.method ?? 'GET', url, body })
      if (url === '/api/notes/reminders/due') return json(200, due)
      if (url === '/api/notifications/updates') return json(200, { updates })
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
const chips = () => [...document.body.querySelectorAll('.notif__chip')]
const click = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent.trim() === text).click()

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  due = [note(1, { title: 'Revisar PR' }), note(2, { title: 'Daily' })]
  updates = []
  routeFetch()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

async function mountBell() {
  const store = useNotificationsStore()
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push('/')
  await router.isReady()
  const wrapper = mount(NotificationBell, { attachTo: document.body, global: { plugins: [router] } })
  await store.poll()
  await flushPromises()
  return { store, wrapper, router }
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

describe('notificações de tarefa da sprint', () => {
  beforeEach(() => {
    updates = [
      update('WAI-1', { kind: 'pr_approved', title: 'PR 7', event_count: 3 }),
      update('WAI-2'),
    ]
  })

  it('as mexidas entram no selo e ficam abaixo dos lembretes na lista', async () => {
    const { store, wrapper } = await mountBell()

    expect(badge().textContent).toBe('4')

    bell().click()
    await flushPromises()

    expect(items().map((li) => li.dataset.key ?? li.dataset.id)).toEqual(['1', '2', 'WAI-1', 'WAI-2'])
    const primeira = items()[2]
    expect(primeira.querySelector('.notif__title').textContent).toContain('WAI-1')
    expect(primeira.querySelector('.notif__what').textContent).toContain('Rafael')
    expect(primeira.querySelector('.notif__when').textContent).toContain('3 novidades')
    expect(store.unseenCount).toBe(0)
    wrapper.unmount()
  })

  it('mexida nova na mesma tarefa volta a somar no selo', async () => {
    const { store, wrapper } = await mountBell()
    store.openPanel()
    store.closePanel()
    await flushPromises()
    expect(badge()).toBeNull()

    updates = [update('WAI-1', { occurred_at: new Date(Date.now() + 60_000).toISOString() }), updates[1]]
    await store.poll()
    await flushPromises()

    expect(badge().textContent).toBe('1')
    wrapper.unmount()
  })

  it('"Abrir na sprint" leva ao canvas da sprint com a tarefa aberta na aba do evento', async () => {
    const ui = useUiStore()
    const { store, wrapper, router } = await mountBell()
    store.openPanel()
    await flushPromises()

    click(items()[2], 'Abrir na sprint')
    await vi.waitFor(() =>
      expect(router.currentRoute.value.fullPath).toBe('/sprints?tarefa=WAI-1&sprint=3995'),
    )
    // PR abre na aba de PRs; comentário abriria no Histórico.
    expect(ui.consumeIssueTab('WAI-1')).toBe('prs')
    expect(store.open).toBe(false)
    wrapper.unmount()
  })

  it('o endpoint fora do ar não derruba os lembretes do painel', async () => {
    const { store, wrapper } = await mountBell()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => (url === '/api/notifications/updates' ? json(500, { detail: 'caiu' }) : json(200, due))),
    )
    await store.poll()
    await flushPromises()

    expect(store.reminders).toHaveLength(2)
    // A última lista boa fica na tela em vez de sumir por causa de um erro de rede.
    expect(store.updates).toHaveLength(2)
    wrapper.unmount()
  })
})

describe('filtro do painel de notificações', () => {
  beforeEach(() => {
    updates = [update('WAI-1'), update('WAI-2')]
  })

  it('cada botão mostra a contagem do seu tipo e filtra a lista', async () => {
    const { store, wrapper } = await mountBell()
    bell().click()
    await flushPromises()

    expect(chips().map((c) => c.textContent.replace(/\s+/g, ' ').trim())).toEqual(['Lembretes 2', 'Tarefas 2'])

    chips()[1].click()
    await flushPromises()

    expect(items().map((li) => li.dataset.key)).toEqual(['WAI-1', 'WAI-2'])
    expect(store.kinds).toEqual(['update'])
    wrapper.unmount()
  })

  it('os dois ligados mostram tudo, e desligar o último tira o filtro', async () => {
    const { store, wrapper } = await mountBell()
    bell().click()
    await flushPromises()

    chips()[0].click()
    chips()[1].click()
    await flushPromises()
    expect(items()).toHaveLength(4)

    chips()[0].click()
    chips()[1].click()
    await flushPromises()

    expect(store.kinds).toEqual([])
    expect(items()).toHaveLength(4)
    wrapper.unmount()
  })

  it('filtro que esconde tudo avisa que é do filtro', async () => {
    due = []
    const { wrapper } = await mountBell()
    bell().click()
    await flushPromises()

    chips()[0].click()
    await flushPromises()

    expect(items()).toHaveLength(0)
    expect(document.body.querySelector('.notif__empty').textContent).toContain('Nada deste tipo')
    wrapper.unmount()
  })

  it('o que o filtro esconde continua somando no selo', async () => {
    const { store, wrapper } = await mountBell()
    store.toggleKind('reminder')
    // Abrir com o filtro ligado só marca como visto o que apareceu na tela.
    bell().click()
    await flushPromises()

    expect(store.unseenCount).toBe(2)
    expect(badge().textContent).toBe('2')
    wrapper.unmount()
  })
})

describe('notificações fixadas no header', () => {
  async function mountBoth() {
    const store = useNotificationsStore()
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/')
    await router.isReady()
    const pins = mount(NotificationPins, { attachTo: document.body })
    const panel = mount(NotificationBell, { attachTo: document.body, global: { plugins: [router] } })
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

    const fixados = [...document.body.querySelectorAll('.pins__open')]
    expect(fixados.map((c) => c.textContent.trim())).toEqual(['Daily'])
    // Só o título: horário e ações ficam na modal e no painel.
    expect(document.body.querySelector('.pins__item').textContent).not.toContain('Concluir')

    store.closePanel()
    await flushPromises()
    fixados[0].click()
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
    expect(JSON.parse(localStorage.getItem('sprintai.notifications.pinned'))).toEqual(['lembrete:1'])

    // Outra sessão do app lendo o mesmo localStorage.
    setActivePinia(createPinia())
    const recarregado = useNotificationsStore()
    expect(recarregado.pinnedIds).toEqual(['lembrete:1'])

    await recarregado.poll()
    expect(recarregado.pinned.map((entry) => entry.note.id)).toEqual([1])
    await recarregado.acknowledge(1)

    expect(recarregado.pinnedIds).toEqual([])
    expect(JSON.parse(localStorage.getItem('sprintai.notifications.pinned'))).toEqual([])
    unmount()
  })

  it('o fixado de antes das tarefas no sino, guardado como número, continua valendo', async () => {
    localStorage.setItem('sprintai.notifications.pinned', JSON.stringify([2]))
    const { store, unmount } = await mountBoth()

    expect(store.pinnedIds).toEqual(['lembrete:2'])
    expect([...document.body.querySelectorAll('.pins__open')].map((c) => c.textContent.trim())).toEqual(['Daily'])
    unmount()
  })

  it('desafixar pelo X do chip tira do header sem mexer no lembrete', async () => {
    const { store, unmount } = await mountBoth()
    store.togglePin('lembrete:1')
    await flushPromises()

    document.body.querySelector('.pins__off').click()
    await flushPromises()

    expect(document.body.querySelector('.pins')).toBeNull()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    unmount()
  })
})
