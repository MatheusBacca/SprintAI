/** Sem acento e em minúsculas — a busca do painel e a do canvas comparam igual. */
export const normalize = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/**
 * Quebra o texto em partes marcando onde o termo aparece, sem diferenciar acento nem
 * caixa. Renderizado como nós de texto (nunca `v-html`).
 */
export function highlightParts(text, term) {
  const needle = normalize((term ?? '').trim())
  if (!text) return []
  if (!needle) return [{ text, hit: false }]
  const haystack = normalize(text)
  const out = []
  let from = 0
  let idx = haystack.indexOf(needle)
  while (idx !== -1) {
    if (idx > from) out.push({ text: text.slice(from, idx), hit: false })
    out.push({ text: text.slice(idx, idx + needle.length), hit: true })
    from = idx + needle.length
    idx = haystack.indexOf(needle, from)
  }
  if (from < text.length) out.push({ text: text.slice(from), hit: false })
  return out
}

/** Trecho de uma linha em volta da primeira ocorrência do termo. */
export function snippetAround(text, term, radius = 70) {
  const flat = (text ?? '').replace(/\s+/g, ' ').trim()
  const needle = normalize((term ?? '').trim())
  const idx = needle ? normalize(flat).indexOf(needle) : -1
  if (idx <= radius) return flat.length > radius * 2 ? `${flat.slice(0, radius * 2)}…` : flat
  const start = idx - radius
  const end = Math.min(flat.length, idx + needle.length + radius)
  return `…${flat.slice(start, end)}${end < flat.length ? '…' : ''}`
}

/** Como `highlightParts`, mas marcando qualquer um dos termos (busca com várias palavras). */
export function highlightTerms(text, terms) {
  if (!text) return []
  const needles = [...new Set((terms ?? []).map((t) => normalize(t.trim())).filter((t) => t.length >= 2))]
  if (!needles.length) return [{ text, hit: false }]
  const haystack = normalize(text)
  const ranges = []
  for (const needle of needles) {
    for (let idx = haystack.indexOf(needle); idx !== -1; idx = haystack.indexOf(needle, idx + needle.length)) {
      ranges.push([idx, idx + needle.length])
    }
  }
  ranges.sort((a, b) => a[0] - b[0])
  const merged = []
  for (const [start, end] of ranges) {
    const last = merged.at(-1)
    if (last && start <= last[1]) last[1] = Math.max(last[1], end)
    else merged.push([start, end])
  }
  const out = []
  let from = 0
  for (const [start, end] of merged) {
    if (start > from) out.push({ text: text.slice(from, start), hit: false })
    out.push({ text: text.slice(start, end), hit: true })
    from = end
  }
  if (from < text.length) out.push({ text: text.slice(from), hit: false })
  return out
}

/** Palavras de uma busca que valem destacar (sem operadores `or`, aspas e `-`). */
export function searchTerms(query) {
  const words = ((query ?? '').match(/[\p{L}\p{N}_-]+/gu) ?? []).map((w) => w.replace(/^-+|-+$/g, ''))
  return [...new Set(words)].filter((w) => w.length >= 2 && !['or', 'and'].includes(w.toLowerCase()))
}
