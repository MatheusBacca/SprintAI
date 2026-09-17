const ALLOWED_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

/** Só deixa passar links http(s)/mailto — conteúdo do Jira é dado de terceiros. */
export function safeUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const url = new URL(value.trim())
    return ALLOWED_PROTOCOLS.has(url.protocol) ? url.href : null
  } catch {
    return null
  }
}
