/** `{ q: 'x', tag: ['a', 'b'], vazio: '' }` → `?q=x&tag=a&tag=b` (ignora vazios). */
export function toQuery(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v))
    else search.append(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
