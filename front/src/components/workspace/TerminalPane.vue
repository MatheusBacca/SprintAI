<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useTerminalsStore } from '@/stores/terminals'
import { useUiStore } from '@/stores/ui'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Um terminal: o xterm.js desenhando um `powershell.exe` de verdade, que mora no terminal
 * host. O xterm desenha num canvas e não interpreta HTML — a saída do shell não vira DOM.
 *
 * - **Cores** saem dos tokens `--term-*` (o xterm não lê CSS) e são relidas ao trocar o tema.
 * - **Links** clicáveis (os de texto e os OSC 8) passam pelo `safeUrl`: `javascript:` vindo
 *   da saída de um comando não abre nada.
 * - **Colar várias linhas** pede confirmação: cada quebra de linha vira um Enter no shell.
 * - **Ctrl+C** com texto selecionado copia; sem seleção, vai para o shell (interrompe).
 */
const props = defineProps({
  session: { type: Object, required: true },
  active: { type: Boolean, default: true },
})

const store = useTerminalsStore()
const ui = useUiStore()
const host = ref(null)

const TERM_COLORS = {
  background: '--term-bg',
  foreground: '--term-fg',
  cursor: '--term-cursor',
  selectionBackground: '--term-selection',
  black: '--term-black',
  red: '--term-red',
  green: '--term-green',
  yellow: '--term-yellow',
  blue: '--term-blue',
  magenta: '--term-magenta',
  cyan: '--term-cyan',
  white: '--term-white',
  brightBlack: '--term-bright-black',
  brightRed: '--term-bright-red',
  brightGreen: '--term-bright-green',
  brightYellow: '--term-bright-yellow',
  brightBlue: '--term-bright-blue',
  brightMagenta: '--term-bright-magenta',
  brightCyan: '--term-bright-cyan',
  brightWhite: '--term-bright-white',
}

function readTheme() {
  const style = getComputedStyle(document.documentElement)
  const theme = {}
  for (const [key, token] of Object.entries(TERM_COLORS)) {
    const value = style.getPropertyValue(token).trim()
    if (value) theme[key] = value
  }
  return theme
}

function openLink(event, uri) {
  const url = safeUrl(uri)
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

let term = null
let fit = null
let observer = null
let writer = null

function refit() {
  if (!term || !fit || !host.value?.offsetWidth) return
  try {
    fit.fit()
  } catch {
    // Sem medida (aba escondida): fica para o próximo redimensionamento.
  }
}

onMounted(() => {
  term = new Terminal({
    fontFamily: getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim() || 'monospace',
    fontSize: 12,
    lineHeight: 1.15,
    cursorBlink: true,
    scrollback: 5000,
    theme: readTheme(),
    linkHandler: { activate: openLink },
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.loadAddon(new WebLinksAddon(openLink))
  term.open(host.value)

  term.attachCustomKeyEventHandler((event) => {
    if (event.type !== 'keydown') return true
    const key = event.key.toLowerCase()
    if (event.ctrlKey && !event.shiftKey && key === 'c' && term.hasSelection()) {
      navigator.clipboard?.writeText(term.getSelection()).catch(() => {})
      term.clearSelection()
      return false
    }
    // Ctrl+V fica com o navegador: o colar passa pelo `paste` abaixo, com a confirmação.
    if (event.ctrlKey && !event.shiftKey && key === 'v') return false
    return true
  })

  host.value.addEventListener(
    'paste',
    (event) => {
      const text = event.clipboardData?.getData('text') ?? ''
      const lines = text.split(/\r?\n/).filter((line) => line.length).length
      if (lines > 1 && !window.confirm(`Colar ${lines} linhas no terminal? Cada linha roda como um comando.`)) {
        event.preventDefault()
        event.stopImmediatePropagation()
      }
    },
    true,
  )

  term.onData((data) => store.input(props.session.id, data))
  term.onResize(({ cols, rows }) => store.resize(props.session.id, cols, rows))

  writer = {
    write: (data) => term.write(data),
    reset: (data) => {
      term.reset()
      if (data) term.write(data)
    },
  }
  store.attach(props.session.id, writer)

  refit()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => refit())
    observer.observe(host.value)
  }
})

watch(
  () => ui.isDark,
  () => {
    if (term) term.options.theme = readTheme()
  },
)

// Aba que volta a aparecer: mede de novo e recebe o foco.
watch(
  () => props.active,
  (active) => {
    if (!active) return
    requestAnimationFrame(() => {
      refit()
      term?.focus()
    })
  },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  store.detach(props.session.id, writer)
  term?.dispose()
  term = null
})

defineExpose({ focus: () => term?.focus() })
</script>

<template>
  <div ref="host" class="pane" data-terminal :data-session="session.id" />
</template>

<style scoped>
.pane {
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 6px 0 0 8px;
  background: var(--term-bg);
}

.pane :deep(.xterm) {
  height: 100%;
}

.pane :deep(.xterm-viewport) {
  background: var(--term-bg) !important;
}
</style>
