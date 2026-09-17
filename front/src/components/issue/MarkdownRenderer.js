/**
 * Renderiza o markdown de um comentário de PR como VNodes do Vue — nunca como
 * HTML cru (`v-html`), pelo mesmo motivo do `AdfRenderer`: o corpo vem do
 * Bitbucket e é dado de terceiro. Link só passa pelo `safeUrl`.
 */
import { h } from 'vue'
import { parseMarkdown } from '@/utils/markdown'
import { safeUrl } from '@/utils/safeUrl'

function renderInline(nodes) {
  return nodes.map((node, key) => {
    switch (node.type) {
      case 'text':
        return node.text
      case 'break':
        return h('br', { key })
      case 'strong':
        return h('strong', { key }, renderInline(node.children))
      case 'em':
        return h('em', { key }, renderInline(node.children))
      case 'strike':
        return h('s', { key }, renderInline(node.children))
      case 'code':
        return h('code', { key, class: 'md-code' }, node.text)
      case 'link': {
        const href = safeUrl(node.href)
        const children = renderInline(node.children)
        // Link recusado não some: o texto dele continua legível, só não clicável.
        return href
          ? h('a', { key, href, target: '_blank', rel: 'noopener noreferrer' }, children)
          : h('span', { key }, children)
      }
      default:
        return null
    }
  })
}

function renderBlock(node, key) {
  switch (node.type) {
    case 'paragraph':
      return h('p', { key }, renderInline(node.inline))
    case 'heading':
      // Desce dois níveis: o título da tela é o h1 e o do comentário não compete com ele.
      return h(`h${Math.min(node.level + 2, 6)}`, { key, class: 'md-heading' }, renderInline(node.inline))
    case 'code':
      return h('pre', { key, class: 'md-pre' }, h('code', node.text))
    case 'list':
      return h(
        node.ordered ? 'ol' : 'ul',
        { key, class: 'md-list', start: node.ordered && node.start !== 1 ? node.start : undefined },
        node.items.map((blocks, i) => h('li', { key: i }, blocks.map(renderBlock))),
      )
    case 'quote':
      return h('blockquote', { key, class: 'md-quote' }, node.blocks.map(renderBlock))
    case 'rule':
      return h('hr', { key, class: 'md-rule' })
    default:
      return null
  }
}

export default {
  name: 'MarkdownRenderer',
  props: {
    source: { type: String, default: '' },
  },
  setup(props) {
    return () => {
      const blocks = parseMarkdown(props.source)
      if (!blocks.length) return null
      return h('div', { class: 'md' }, blocks.map(renderBlock))
    }
  },
}
