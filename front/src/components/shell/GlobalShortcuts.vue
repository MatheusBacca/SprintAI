<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useNotesStore } from '@/stores/notes'
import { useScreenContextStore } from '@/stores/screenContext'
import { useSearchStore } from '@/stores/search'
import { useShortcutsStore } from '@/stores/shortcuts'
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

const MAX_BODY = 20_000
const MAX_ISSUES = 30

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
}

function onKeydown(event) {
  if (shortcuts.recording || event.repeat || event.isComposing || event.defaultPrevented) return
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
