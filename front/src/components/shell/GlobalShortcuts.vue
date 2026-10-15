<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useHealthStore } from '@/stores/health'
import { useNotesStore } from '@/stores/notes'
import { useNotificationsStore } from '@/stores/notifications'
import { useRepoIssuesStore } from '@/stores/repoIssues'
import { useScreenContextStore } from '@/stores/screenContext'
import { useSearchStore } from '@/stores/search'
import { useShortcutsStore } from '@/stores/shortcuts'
import { useSyncStore } from '@/stores/sync'
import { comboFromEvent, issueKeysIn, readSelection, searchTermFrom } from '@/utils/shortcuts'

/**
 * Atalhos de teclado válidos em qualquer tela (F4.1). Sem template: só escuta o
 * teclado e aciona os stores. Todo atalho aceito tem Ctrl/Alt ou é tecla F, então
 * disparar com o foco num campo de texto não atrapalha a digitação — e permite usar
 * o texto selecionado dentro do próprio campo.
 */
const notes = useNotesStore()
const screen = useScreenContextStore()
const shortcuts = useShortcutsStore()
const search = useSearchStore()
const notifications = useNotificationsStore()
const repoIssues = useRepoIssuesStore()
const health = useHealthStore()
const sync = useSyncStore()

const MAX_BODY = 20_000
const MAX_ISSUES = 30

/**
 * Painéis do topo abertos pelo teclado: abrir um fecha os outros. Pelo mouse quem fecha é
 * o clique fora — que, com a tecla, não aconteceu.
 */
function closeTopPanels() {
  if (notes.palette.open) notes.closePalette()
  if (search.open) search.close()
  notifications.closePanel()
  repoIssues.closePanel()
}

/** Abre o painel ancorado ou, aberto, fecha — a mesma tecla vai e volta. */
function togglePanel(store) {
  if (notes.editor.open) return
  if (store.open) {
    store.closePanel()
    return
  }
  closeTopPanels()
  store.openPanel()
}

const handlers = {
  open_reminders() {
    if (notes.editor.open) return
    if (notes.palette.open) {
      notes.closePalette()
      return
    }
    const selected = searchTermFrom(readSelection())
    if (selected) notes.openPalette(selected, 'selection')
    else if (screen.focusedIssueKey) notes.openPalette(screen.focusedIssueKey, 'issue')
    else notes.openPalette('', null)
  },

  new_reminder() {
    if (notes.editor.open) return
    const selected = readSelection().trim().slice(0, MAX_BODY)
    const keys = [...new Set([...issueKeysIn(selected), screen.focusedIssueKey].filter(Boolean))]
    if (notes.palette.open) notes.closePalette()
    notes.openEditor(null, { body: selected, issue_keys: keys.slice(0, MAX_ISSUES) })
  },

  global_search() {
    if (notes.editor.open) return
    if (search.open) {
      search.close()
      return
    }
    if (notes.palette.open) notes.closePalette()
    search.openSearch(searchTermFrom(readSelection()) || null)
  },

  open_notifications() {
    togglePanel(notifications)
  },

  open_repo_issues() {
    togglePanel(repoIssues)
  },

  sync_now() {
    // As travas do botão: sem API, sem status do sync ou com um sync já andando, nada.
    if (health.level !== 'ok' || sync.statusError || sync.running || sync.triggering) return
    sync.trigger()
  },
}

function onKeydown(event) {
  if (shortcuts.recording || event.repeat || event.isComposing || event.defaultPrevented) return
  // No terminal do Workspace a tecla é do shell: Ctrl+K, Ctrl+Shift+L e cia. vão para ele.
  if (event.target?.closest?.('[data-terminal]')) return
  const combo = comboFromEvent(event)
  const action = combo && shortcuts.actionFor(combo)
  if (!action || !handlers[action]) return
  // Atalho configurado nunca cai na ação do navegador, mesmo quando ignorado aqui.
  event.preventDefault()
  event.stopPropagation()
  handlers[action]()
}

onMounted(() => {
  if (!shortcuts.loaded) shortcuts.load()
  // Captura: roda antes dos handlers de teclado das telas (drawer, canvas, editor).
  window.addEventListener('keydown', onKeydown, true)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown, true))

defineExpose({ onKeydown })
</script>

<template>
  <span hidden />
</template>
