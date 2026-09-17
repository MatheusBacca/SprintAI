import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, CLIENT_HEADER } from '@/services/api'

function mockFetch(status, body) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('envia o header X-SprintAI em todo request', async () => {
    const fetchMock = mockFetch(200, { ok: true })

    await api.get('/health')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/health')
    expect(init.headers[CLIENT_HEADER]).toBe('1')
  })

  it('serializa body JSON em escrita', async () => {
    const fetchMock = mockFetch(200, {})

    await api.post('/notes', { title: 'x' })

    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe('{"title":"x"}')
  })

  it('lança ApiError com detail da API', async () => {
    mockFetch(403, { detail: 'Origem não permitida' })

    await expect(api.get('/health')).rejects.toMatchObject({
      name: 'ApiError',
      status: 403,
      message: 'Origem não permitida',
    })
    await expect(api.get('/health')).rejects.toBeInstanceOf(ApiError)
  })
})
