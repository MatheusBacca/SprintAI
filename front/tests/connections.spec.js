import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import SettingsView from '@/views/SettingsView.vue'
import { useConnectionsStore } from '@/stores/connections'
import { formatRelative } from '@/utils/time'
import { routes } from '@/router/routes'

async function mountSettings(query = '') {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(`/configuracoes${query}`)
  await router.isReady()
  return mount(SettingsView, { global: { plugins: [router] } })
}

const NOW = new Date().toISOString()

const JIRA_OK = {
  provider: 'jira',
  configured: true,
  account_name: 'Matheus Bacca',
  validated_at: NOW,
  last_checked_at: NOW,
  last_error: null,
  settings: { site_url: 'https://weon.atlassian.net', email: 'matheus.bacca@weon.com.br', auth_mode: 'classic' },
}
const BB_EMPTY = { provider: 'bitbucket', configured: false, settings: {} }

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

/** Roteia chamadas por "MÉTODO caminho". */
function routeFetch(routes) {
  const fn = vi.fn(async (url, init) => {
    const key = `${init.method} ${url}`
    const handler = routes[key]
    if (!handler) throw new Error(`fetch não mockado: ${key}`)
    return typeof handler === 'function' ? handler(init) : handler
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

describe('connections store', () => {
  it('carrega o status dos provedores', async () => {
    routeFetch({ 'GET /api/connections': jsonResponse(200, [JIRA_OK, BB_EMPTY]) })
    const store = useConnectionsStore()

    await store.load()

    expect(store.jira.account_name).toBe('Matheus Bacca')
    expect(store.bitbucket.configured).toBe(false)
  })

  it('mostra o motivo quando o teste recusa o cadastro', async () => {
    routeFetch({
      'PUT /api/connections/jira': jsonResponse(422, { detail: 'Jira: credenciais inválidas (e-mail ou token).' }),
    })
    const store = useConnectionsStore()

    const ok = await store.save('jira', {})

    expect(ok).toBe(false)
    expect(store.feedback.jira).toEqual({ type: 'error', text: 'Jira: credenciais inválidas (e-mail ou token).' })
    expect(store.jira.configured).toBe(false)
  })

  it('traduz erro de validação do FastAPI em texto', async () => {
    routeFetch({
      'PUT /api/connections/jira': jsonResponse(422, {
        detail: [{ loc: ['body', 'site_url'], msg: 'Value error, Use o endereço do Jira Cloud', type: 'value_error' }],
      }),
    })
    const store = useConnectionsStore()

    await store.save('jira', {})

    expect(store.feedback.jira.text).toBe('Use o endereço do Jira Cloud')
  })

  it('teste que falha atualiza o status com o erro', async () => {
    routeFetch({
      'POST /api/connections/jira/test': jsonResponse(200, {
        ok: false,
        message: 'Jira: token sem permissão — confira os escopos.',
        status: { ...JIRA_OK, last_error: 'Jira: token sem permissão — confira os escopos.' },
      }),
    })
    const store = useConnectionsStore()

    await store.test('jira')

    expect(store.feedback.jira.type).toBe('error')
    expect(store.jira.last_error).toContain('sem permissão')
  })
})

describe('SettingsView', () => {
  it('salva o Jira, limpa o campo de token e mostra a conta conectada', async () => {
    let sentBody
    routeFetch({
      'GET /api/connections': jsonResponse(200, [{ provider: 'jira', configured: false, settings: {} }, BB_EMPTY]),
      'PUT /api/connections/jira': (init) => {
        sentBody = JSON.parse(init.body)
        return jsonResponse(200, JIRA_OK)
      },
    })
    const wrapper = await mountSettings()
    await flushPromises()

    const jiraCard = wrapper.findAll('.conn')[0]
    await jiraCard.find('input[type="email"]').setValue('matheus.bacca@weon.com.br')
    await jiraCard.find('input[type="password"]').setValue('ATATT3xFfGF0-token-jira-123456')
    await jiraCard.find('form').trigger('submit')
    await flushPromises()

    expect(sentBody).toMatchObject({
      site_url: 'https://weon.atlassian.net',
      email: 'matheus.bacca@weon.com.br',
      auth_mode: 'classic',
      api_token: 'ATATT3xFfGF0-token-jira-123456',
    })
    expect(jiraCard.find('input[type="password"]').element.value).toBe('')
    expect(jiraCard.find('.conn__chip').text()).toContain('Conectado')
    expect(jiraCard.text()).toContain('Matheus Bacca')
  })

  it('reenvia sem token quando o campo fica vazio (mantém o salvo)', async () => {
    let sentBody
    routeFetch({
      'GET /api/connections': jsonResponse(200, [JIRA_OK, BB_EMPTY]),
      'PUT /api/connections/jira': (init) => {
        sentBody = JSON.parse(init.body)
        return jsonResponse(200, JIRA_OK)
      },
    })
    const wrapper = await mountSettings()
    await flushPromises()

    const jiraCard = wrapper.findAll('.conn')[0]
    expect(jiraCard.find('input[type="password"]').attributes('placeholder')).toContain('Cofre do Windows')
    await jiraCard.find('form').trigger('submit')
    await flushPromises()

    expect(sentBody.api_token).toBeNull()
  })

  it('remoção pede confirmação antes de chamar a API', async () => {
    const fetchMock = routeFetch({
      'GET /api/connections': jsonResponse(200, [JIRA_OK, BB_EMPTY]),
      'DELETE /api/connections/jira': { ok: true, status: 204, headers: new Headers(), text: async () => '' },
    })
    const wrapper = await mountSettings()
    await flushPromises()

    const removeBtn = wrapper.findAll('.conn')[0].find('.btn--ghost-danger')
    await removeBtn.trigger('click')
    expect(removeBtn.text()).toBe('Confirmar remoção')
    expect(fetchMock.mock.calls.some(([, init]) => init.method === 'DELETE')).toBe(false)

    await removeBtn.trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls.some(([, init]) => init.method === 'DELETE')).toBe(true)
    expect(wrapper.findAll('.conn')[0].find('.conn__chip').text()).toContain('Não configurado')
  })

  it('OpenAI aparece desabilitada até o M4', async () => {
    routeFetch({ 'GET /api/connections': jsonResponse(200, [JIRA_OK, BB_EMPTY]) })
    const wrapper = await mountSettings()
    await flushPromises()

    const openai = wrapper.findAll('.conn')[2]
    expect(openai.classes()).toContain('conn--disabled')
    expect(openai.find('.conn__actions').exists()).toBe(false)
  })
})

describe('formatRelative', () => {
  const now = new Date('2026-09-14T12:00:00Z')

  it.each([
    ['2026-09-14T11:59:50Z', 'agora mesmo'],
    ['2026-09-14T11:55:00Z', 'há 5 minutos'],
    ['2026-09-14T09:00:00Z', 'há 3 horas'],
    ['2026-09-13T12:00:00Z', 'ontem'],
  ])('%s → %s', (value, expected) => {
    expect(formatRelative(value, now)).toBe(expected)
  })

  it('devolve null para vazio ou inválido', () => {
    expect(formatRelative(null)).toBeNull()
    expect(formatRelative('não é data')).toBeNull()
  })
})
