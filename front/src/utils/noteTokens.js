import { normalize } from './highlight'

/** Tag de lembrete: sem `#`, minúscula, espaço vira hífen — "Boas praticas" → "boas-praticas". */
export const normalizeTag = (value) =>
  value.replace(/^#/, '').trim().toLowerCase().replace(/\s+/g, '-').slice(0, 40) || null

export const ISSUE_KEY = /^[A-Z][A-Z0-9]{1,9}-\d{1,7}$/

/** Chave de tarefa em maiúsculas, ou `null` se não for uma. */
export const normalizeKey = (value) => {
  const key = value.trim().replace(/^@/, '').toUpperCase()
  return ISSUE_KEY.test(key) ? key : null
}

/** Slug de repositório do Bitbucket (mesma regra do back). */
export const normalizeRepo = (value) => {
  const repo = value.trim().replace(/^@/, '').toLowerCase()
  return /^[a-z0-9][a-z0-9._-]{0,99}$/.test(repo) ? repo : null
}

/** Para casar sugestão com o que foi digitado: sem acento, sem caixa, espaço = hífen. */
export const fold = (value) => normalize(value).replace(/\s+/g, '-')

// `#tag` ou `@menção` no começo de uma palavra. Pontuação colada no fim ("@monitoria.")
// não faz parte do nome.
const MENTION = /(^|\s)([#@])([^\s#@]+)/gu
const TRAILING = /[.,;:!?)\]}'"]+$/u

function* scan(text) {
  for (const match of (text ?? '').matchAll(MENTION)) {
    const raw = match[3].replace(TRAILING, '')
    if (!raw) continue
    const start = match.index + match[1].length
    const char = match[2]
    let kind = 'tag'
    let value = normalizeTag(raw)
    if (char === '@') {
      value = normalizeKey(raw)
      kind = 'issue'
      if (!value) {
        value = normalizeRepo(raw)
        kind = 'repo'
      }
    }
    if (value) yield { kind, value, start, end: start + 1 + raw.length }
  }
}

/** Tags, tarefas e repositórios citados no texto — o que a limpeza do blur compara. */
export function mentionsIn(text) {
  const found = { tag: new Set(), issue: new Set(), repo: new Set() }
  for (const m of scan(text)) found[m.kind].add(m.value)
  return found
}

/**
 * Texto quebrado em partes para pintar as menções que viraram vínculo (`marks` =
 * `{ tag, issue, repo }` com as listas do lembrete). Menção que não está vinculada
 * fica texto comum: pintar prometeria um vínculo que não existe.
 */
export function mentionParts(text, marks) {
  const parts = []
  let cursor = 0
  for (const m of scan(text)) {
    if (!marks[m.kind]?.includes(m.value)) continue
    if (m.start > cursor) parts.push({ text: text.slice(cursor, m.start), kind: null })
    parts.push({ text: text.slice(m.start, m.end), kind: m.kind })
    cursor = m.end
  }
  if (cursor < (text ?? '').length) parts.push({ text: text.slice(cursor), kind: null })
  return parts
}
