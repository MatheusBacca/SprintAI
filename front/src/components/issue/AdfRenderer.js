/**
 * Renderiza Atlassian Document Format como VNodes do Vue — nunca como HTML cru
 * (`v-html`), então texto vindo do Jira não consegue injetar markup ou script.
 * Nós desconhecidos caem para os filhos (ou somem, se não tiverem conteúdo).
 */
import { h } from 'vue'
import { safeUrl } from '@/utils/safeUrl'

const PANEL_TONES = new Set(['info', 'note', 'success', 'warning', 'error'])

function children(node, ctx) {
  return (node.content ?? []).map((child, i) => renderNode(child, ctx, i))
}

function renderText(node, key) {
  let vnode = node.text ?? ''
  for (const mark of node.marks ?? []) {
    switch (mark.type) {
      case 'strong':
        vnode = h('strong', vnode)
        break
      case 'em':
        vnode = h('em', vnode)
        break
      case 'strike':
        vnode = h('s', vnode)
        break
      case 'underline':
        vnode = h('u', vnode)
        break
      case 'code':
        vnode = h('code', { class: 'adf-code' }, vnode)
        break
      case 'subsup':
        vnode = h(mark.attrs?.type === 'sup' ? 'sup' : 'sub', vnode)
        break
      case 'link': {
        const href = safeUrl(mark.attrs?.href)
        vnode = href ? h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, vnode) : vnode
        break
      }
      default:
        break
    }
  }
  return typeof vnode === 'string' ? h('span', { key }, vnode) : vnode
}

function renderNode(node, ctx, key) {
  if (!node || typeof node !== 'object') return null
  const attrs = node.attrs ?? {}

  switch (node.type) {
    case 'doc':
      return h('div', { class: 'adf', key }, children(node, ctx))
    case 'text':
      return renderText(node, key)
    case 'paragraph':
      return h('p', { key }, children(node, ctx))
    case 'heading': {
      const level = Math.min(Math.max(Number(attrs.level) || 3, 1), 6)
      // Dentro do painel os títulos descem dois níveis (o título do painel é o h2).
      return h(`h${Math.min(level + 2, 6)}`, { key, class: 'adf-heading' }, children(node, ctx))
    }
    case 'bulletList':
      return h('ul', { key }, children(node, ctx))
    case 'orderedList':
      return h('ol', { key, start: attrs.order ?? undefined }, children(node, ctx))
    case 'listItem':
      return h('li', { key }, children(node, ctx))
    case 'taskList':
      return h('ul', { key, class: 'adf-tasks' }, children(node, ctx))
    case 'taskItem':
      return h('li', { key, class: 'adf-task' }, [
        h('input', { type: 'checkbox', checked: attrs.state === 'DONE', disabled: true }),
        h('span', children(node, ctx)),
      ])
    case 'blockquote':
      return h('blockquote', { key }, children(node, ctx))
    case 'codeBlock':
      return h('pre', { key, class: 'adf-pre' }, h('code', (node.content ?? []).map((t) => t.text ?? '').join('')))
    case 'rule':
      return h('hr', { key })
    case 'hardBreak':
      return h('br', { key })
    case 'panel': {
      const tone = PANEL_TONES.has(attrs.panelType) ? attrs.panelType : 'info'
      return h('div', { key, class: ['adf-panel', `adf-panel--${tone}`] }, children(node, ctx))
    }
    case 'expand':
    case 'nestedExpand':
      return h('details', { key, class: 'adf-expand' }, [h('summary', attrs.title || 'Detalhes'), ...children(node, ctx)])
    case 'mention':
      return h('span', { key, class: 'adf-mention' }, attrs.text || '@menção')
    case 'emoji':
      return h('span', { key }, attrs.text || attrs.shortName || '')
    case 'status':
      return h('span', { key, class: 'adf-status' }, attrs.text || '')
    case 'date': {
      const ts = Number(attrs.timestamp)
      return h('span', { key, class: 'adf-date' }, Number.isFinite(ts) ? new Date(ts).toLocaleDateString('pt-BR') : '')
    }
    case 'inlineCard':
    case 'blockCard':
    case 'embedCard': {
      const href = safeUrl(attrs.url)
      return href ? h('a', { key, href, target: '_blank', rel: 'noopener noreferrer', class: 'adf-card' }, href) : null
    }
    case 'mediaSingle':
    case 'mediaGroup':
    case 'media':
    case 'mediaInline':
      // Anexos exigem autenticação no Jira: mostramos um marcador em vez da imagem.
      return node.type === 'media' || node.type === 'mediaInline'
        ? h('span', { key, class: 'adf-media' }, `📎 ${attrs.alt || 'anexo'} (abrir no Jira)`)
        : h('div', { key }, children(node, ctx))
    case 'table':
      return h('div', { key, class: 'adf-table-wrap' }, h('table', { class: 'adf-table' }, h('tbody', children(node, ctx))))
    case 'tableRow':
      return h('tr', { key }, children(node, ctx))
    case 'tableHeader':
      return h('th', { key, colspan: attrs.colspan, rowspan: attrs.rowspan }, children(node, ctx))
    case 'tableCell':
      return h('td', { key, colspan: attrs.colspan, rowspan: attrs.rowspan }, children(node, ctx))
    default:
      return node.content ? h('div', { key }, children(node, ctx)) : null
  }
}

export default {
  name: 'AdfRenderer',
  props: {
    doc: { type: Object, default: null },
    fallback: { type: String, default: '' },
  },
  setup(props) {
    return () => {
      if (props.doc && props.doc.type === 'doc' && props.doc.content?.length) {
        return renderNode(props.doc, {}, 'root')
      }
      return props.fallback ? h('p', { class: 'adf adf--plain' }, props.fallback) : h('p', { class: 'adf adf--empty' }, 'Sem descrição.')
    }
  },
}
