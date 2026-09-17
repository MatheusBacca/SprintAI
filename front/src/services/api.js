/**
 * Cliente HTTP da API local.
 *
 * Todo request leva o header `X-SprintAI`: a API recusa chamadas sem ele, o que
 * força preflight de CORS e impede que outro site aberto no navegador chame a API
 * local por baixo dos panos.
 */
export const API_BASE = '/api'
export const CLIENT_HEADER = 'X-SprintAI'

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = { [CLIENT_HEADER]: '1' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  })

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(isJson ? payload : null, response.status, path), payload)
  }
  return payload
}

/** `detail` vem como texto (erro de negócio) ou lista (erro de validação do FastAPI). */
function errorMessage(payload, status, path) {
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((e) => String(e.msg ?? '').replace(/^Value error, /, '')).join(' ')
  }
  return `Erro ${status} em ${path}`
}

export const api = {
  get: (path, opts) => request(path, { ...opts, method: 'GET' }),
  post: (path, body, opts) => request(path, { ...opts, method: 'POST', body }),
  put: (path, body, opts) => request(path, { ...opts, method: 'PUT', body }),
  patch: (path, body, opts) => request(path, { ...opts, method: 'PATCH', body }),
  delete: (path, opts) => request(path, { ...opts, method: 'DELETE' }),
}
