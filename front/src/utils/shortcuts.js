/**
 * Atalhos globais (F4.1). Formato canônico: `Ctrl`, `Alt`, `Shift` nessa ordem + uma
 * tecla (`A`-`Z`, `0`-`9`, `F1`-`F12`, `Space`). As regras espelham
 * `back/services/shortcuts.py`, que é quem valida o que é salvo.
 */

export const SHORTCUT_ACTIONS = [
  {
    id: 'open_reminders',
    label: 'Abrir lembretes',
    description: 'Modal de busca de lembretes, já filtrada pelo texto selecionado na tela ou pela tarefa aberta.',
  },
  {
    id: 'new_reminder',
    label: 'Novo lembrete com a seleção',
    description: 'Abre o editor com o texto selecionado no corpo e as tarefas citadas (ou a aberta) vinculadas.',
  },
  {
    id: 'global_search',
    label: 'Busca global',
    description: 'Busca em tarefas, comentários, PRs, contextos e lembretes, já com o texto selecionado.',
  },
]

export const DEFAULT_BINDINGS = {
  open_reminders: 'Ctrl+Shift+L',
  // Ctrl+Shift+N é reservado pelo Chrome/Edge (janela anônima): a página nunca recebe.
  new_reminder: 'Ctrl+Shift+A',
  global_search: 'Ctrl+K',
}

const MODIFIERS = ['Ctrl', 'Alt', 'Shift']
const KEY = /^(?:[A-Z0-9]|F(?:[1-9]|1[0-2])|Space)$/

export const RESERVED = new Set([
  'Ctrl+Shift+N',
  'Ctrl+Shift+T',
  'Ctrl+Shift+W',
  'Ctrl+Shift+Q',
  'Ctrl+Shift+R',
  'Ctrl+Shift+I',
  'Ctrl+Shift+J',
  'Ctrl+Shift+C',
  'Ctrl+Shift+V',
  'Ctrl+Shift+Z',
  'Ctrl+F4',
  'Ctrl+F5',
  'Alt+F4',
  'Alt+D',
  'Alt+E',
  'Alt+F',
  'Alt+Space',
  'Shift+F10',
])
// Ctrl + tecla sozinho é recusado, menos a convenção de busca dos apps web.
const CTRL_ALLOWED = new Set(['Ctrl+K'])
const RESERVED_FKEYS = new Set(['F1', 'F3', 'F5', 'F6', 'F7', 'F10', 'F11', 'F12'])

/** Tecla física do evento (independe do layout ABNT2/US e do Shift). */
function keyFromCode(code) {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3)
  if (/^Digit[0-9]$/.test(code)) return code.slice(5)
  if (/^F(?:[1-9]|1[0-2])$/.test(code)) return code
  if (code === 'Space') return 'Space'
  return null
}

/** Plano B quando o evento não traz `code` (teclados virtuais, automação). */
function keyFromKey(key) {
  if (/^[a-z0-9]$/i.test(key)) return key.toUpperCase()
  if (/^F(?:[1-9]|1[0-2])$/.test(key)) return key
  if (key === ' ') return 'Space'
  return null
}

/** Atalho canônico de um `keydown`, ou `null` (só modificador, Win/Meta ou tecla não suportada). */
export function comboFromEvent(event) {
  if (event.metaKey) return null
  const key = event.code ? keyFromCode(event.code) : keyFromKey(event.key)
  if (!key) return null
  const mods = []
  if (event.ctrlKey) mods.push('Ctrl')
  if (event.altKey) mods.push('Alt')
  if (event.shiftKey) mods.push('Shift')
  return [...mods, key].join('+')
}

/** Mensagem de erro do atalho (ou `null` se ele pode ser usado). */
export function validateCombo(combo) {
  const parts = (combo ?? '').split('+').filter(Boolean)
  if (!parts.length) return 'Atalho vazio.'
  const key = parts.at(-1)
  const mods = parts.slice(0, -1)
  if (mods.some((m) => !MODIFIERS.includes(m)) || new Set(mods).size !== mods.length) return 'Modificador inválido.'
  if (!KEY.test(key)) return 'Use uma letra, um número, F1–F12 ou Espaço como tecla.'
  const canonical = [...MODIFIERS.filter((m) => mods.includes(m)), key].join('+')
  const isFKey = /^F\d/.test(key)

  if (mods.includes('Ctrl') && mods.includes('Alt')) return 'Ctrl+Alt equivale ao AltGr e digita caracteres (ñ, €…). Use Ctrl+Shift.'
  if (RESERVED.has(canonical) || (!mods.length && RESERVED_FKEYS.has(key))) return `${canonical} é reservado pelo navegador ou pelo Windows.`
  if (!isFKey && !mods.includes('Ctrl') && !mods.includes('Alt')) return 'Combine a tecla com Ctrl ou Alt para não atrapalhar a digitação.'
  if (!isFKey && mods.length === 1 && mods[0] === 'Ctrl' && !CTRL_ALLOWED.has(canonical)) return 'Ctrl + tecla é dos atalhos de edição e do navegador. Use Ctrl+Shift.'
  return null
}

/** Ação (diferente de `exceptAction`) que já usa o atalho. */
export function conflictingAction(bindings, combo, exceptAction) {
  const found = Object.entries(bindings).find(([action, value]) => action !== exceptAction && value === combo)
  return found ? SHORTCUT_ACTIONS.find((a) => a.id === found[0]) ?? { id: found[0], label: found[0] } : null
}

/** `Ctrl+Shift+L` → `['Ctrl', 'Shift', 'L']` para exibir como teclas. */
export function comboKeys(combo) {
  return combo ? combo.split('+').map((k) => (k === 'Space' ? 'Espaço' : k)) : []
}

const TEXT_INPUT_TYPES = new Set(['text', 'search', 'url', 'email', ''])

/**
 * Texto selecionado agora: dentro de um campo de texto focado ou na página.
 * Nunca lê seleção de campo de senha.
 */
export function readSelection(doc = document) {
  const el = doc.activeElement
  const isTextField =
    el && (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && TEXT_INPUT_TYPES.has((el.getAttribute('type') ?? '').toLowerCase())))
  if (isTextField) {
    const { selectionStart: start, selectionEnd: end } = el
    if (start != null && end != null && end > start) return el.value.slice(start, end)
  }
  if (el?.tagName === 'INPUT') return ''
  return doc.getSelection?.()?.toString() ?? ''
}

const ISSUE_KEY = /\b[A-Z][A-Z0-9]{1,9}-\d{1,7}\b/g

export function issueKeysIn(text) {
  return [...new Set((text ?? '').match(ISSUE_KEY) ?? [])]
}

/** Seleção → termo de busca de uma linha. */
export function searchTermFrom(text, max = 120) {
  return (text ?? '').replace(/\s+/g, ' ').trim().slice(0, max).trim()
}

/** "retry exponencial no client" → `retry or exponencial or client` (websearch_to_tsquery). */
export function anyWordQuery(term) {
  const words = [...new Set((term ?? '').match(/[\p{L}\p{N}][\p{L}\p{N}_-]*/gu) ?? [])]
  return words.length > 1 ? words.slice(0, 8).join(' or ') : null
}
