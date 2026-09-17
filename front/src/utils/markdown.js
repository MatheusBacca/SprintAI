/**
 * Markdown → árvore de nós, para o `MarkdownRenderer` virar VNodes.
 *
 * Subconjunto de propósito: é o que aparece numa review de PR do Bitbucket —
 * títulos, ênfase, código, listas, citação, regra e link. Nada de HTML embutido:
 * o corpo do comentário é dado de terceiro, e a única saída daqui é uma árvore
 * que o Vue desenha como texto. Por isso também não entra biblioteca de markdown:
 * todas devolvem string de HTML, que exigiria `v-html`.
 *
 * Função pura, sem Vue — os testes exercitam a árvore direto.
 */

const FENCE = /^ {0,3}(```|~~~)\s*([^\s`]+)?\s*$/
const HEADING = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/
const RULE = /^ {0,3}([-*_])(?:\s*\1){2,}\s*$/
const QUOTE = /^ {0,3}> ?(.*)$/
const BULLET = /^(\s*)([-*+])\s+(.*)$/
const ORDERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/

function isBlockStart(line) {
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    RULE.test(line) ||
    QUOTE.test(line) ||
    BULLET.test(line) ||
    ORDERED.test(line)
  )
}

function listMatch(line) {
  const ordered = ORDERED.exec(line)
  if (ordered) {
    return { ordered: true, indent: ordered[1].length, start: Number(ordered[2]), text: ordered[3] }
  }
  const bullet = BULLET.exec(line)
  if (bullet) return { ordered: false, indent: bullet[1].length, text: bullet[3] }
  return null
}

function parseList(lines, start) {
  const first = listMatch(lines[start])
  const items = []
  let current = null
  let contentIndent = 0
  let i = start

  while (i < lines.length) {
    const line = lines[i]
    const item = listMatch(line)

    if (item && item.indent <= first.indent + 1 && item.ordered === first.ordered) {
      current = [item.text]
      items.push(current)
      // O conteúdo do item começa depois do marcador; é por aí que a continuação alinha.
      contentIndent = line.length - line.trimStart().length + (line.trimStart().match(/^\S+\s+/)?.[0].length ?? 2)
      i += 1
      continue
    }
    if (!current) break

    if (!line.trim()) {
      // Linha em branco só continua a lista se o que vem depois ainda pertence ao item.
      const next = lines[i + 1]
      if (next === undefined) break
      const nextIndent = next.length - next.trimStart().length
      if (!next.trim() || (nextIndent < contentIndent && !listMatch(next))) break
      current.push('')
      i += 1
      continue
    }

    const indent = line.length - line.trimStart().length
    if (indent < contentIndent && !listMatch(line)) break
    current.push(line.slice(Math.min(indent, contentIndent)))
    i += 1
  }

  const node = {
    type: 'list',
    ordered: first.ordered,
    start: first.ordered ? first.start : undefined,
    items: items.map((raw) => parseBlocks(raw)),
  }
  return [node, i]
}

function parseBlocks(lines) {
  const blocks = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (!line.trim()) {
      i += 1
      continue
    }

    const fence = FENCE.exec(line)
    if (fence) {
      const body = []
      i += 1
      while (i < lines.length && !new RegExp(`^ {0,3}${fence[1]}\\s*$`).test(lines[i])) {
        body.push(lines[i])
        i += 1
      }
      i += 1 // fecha a cerca (ou acabou o texto)
      blocks.push({ type: 'code', lang: fence[2] ?? null, text: body.join('\n') })
      continue
    }

    if (RULE.test(line)) {
      blocks.push({ type: 'rule' })
      i += 1
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        inline: parseInline(heading[2]),
      })
      i += 1
      continue
    }

    if (QUOTE.test(line)) {
      const body = []
      while (i < lines.length && QUOTE.test(lines[i])) {
        body.push(QUOTE.exec(lines[i])[1])
        i += 1
      }
      blocks.push({ type: 'quote', blocks: parseBlocks(body) })
      continue
    }

    if (listMatch(line)) {
      const [node, next] = parseList(lines, i)
      blocks.push(node)
      i = next
      continue
    }

    const paragraph = []
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      paragraph.push(lines[i].trim())
      i += 1
    }
    if (paragraph.length) blocks.push({ type: 'paragraph', inline: parseInline(paragraph.join('\n')) })
  }

  return blocks
}

const WORD = /[\wÀ-ɏ]/

/**
 * `_ênfase_` só vale entre não-palavras: sem isso, `WAI_8360_api` viraria itálico
 * no meio de um nome de branch — que é justamente o que mais aparece numa review.
 */
function underscoreIsEmphasis(text, index, length) {
  const before = text[index - 1]
  const after = text[index + length]
  return !(before && WORD.test(before)) && !(after && WORD.test(after))
}

const INLINE_RULES = [
  { re: /`([^`]+)`/, node: (m) => ({ type: 'code', text: m[1] }) },
  {
    re: /!?\[([^\]]*)\]\(\s*([^\s)]+)(?:\s+"[^"]*")?\s*\)/,
    node: (m) => ({ type: 'link', href: m[2], children: parseInline(m[1]) }),
  },
  { re: /\*\*([\s\S]+?)\*\*/, node: (m) => ({ type: 'strong', children: parseInline(m[1]) }) },
  {
    re: /__([\s\S]+?)__/,
    node: (m) => ({ type: 'strong', children: parseInline(m[1]) }),
    guardUnderscore: true,
  },
  { re: /~~([\s\S]+?)~~/, node: (m) => ({ type: 'strike', children: parseInline(m[1]) }) },
  { re: /\*([^*\n]+?)\*/, node: (m) => ({ type: 'em', children: parseInline(m[1]) }) },
  {
    re: /_([^_\n]+?)_/,
    node: (m) => ({ type: 'em', children: parseInline(m[1]) }),
    guardUnderscore: true,
  },
]

function pushText(out, text) {
  if (!text) return
  // Quebra simples vira quebra de linha: é como o Bitbucket mostra um comentário.
  const parts = text.split('\n')
  parts.forEach((part, i) => {
    if (i) out.push({ type: 'break' })
    if (part) out.push({ type: 'text', text: part })
  })
}

export function parseInline(text) {
  const out = []
  let rest = String(text ?? '')

  while (rest) {
    let best = null
    for (const rule of INLINE_RULES) {
      const match = rule.re.exec(rest)
      if (!match) continue
      if (rule.guardUnderscore && !underscoreIsEmphasis(rest, match.index, match[0].length)) continue
      if (!best || match.index < best.match.index) best = { rule, match }
    }
    if (!best) break

    pushText(out, rest.slice(0, best.match.index))
    out.push(best.rule.node(best.match))
    rest = rest.slice(best.match.index + best.match[0].length)
  }

  pushText(out, rest)
  return out
}

export function parseMarkdown(source) {
  return parseBlocks(
    String(source ?? '')
      .replace(/\r\n?/g, '\n')
      .split('\n'),
  )
}
