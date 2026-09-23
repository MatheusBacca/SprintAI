<script setup>
import { ChevronDown } from 'lucide-vue-next'
import { useJiraActionsStore } from '@/stores/jiraActions'

/**
 * Selo de status do Jira que abre a linha de fluxo para mover a tarefa. A aparência
 * (contorno, cor, posição) é de quem usa — a classe passada cai na raiz —; aqui só entra
 * o que faz dele um botão.
 *
 * `nodrag nopan`: dentro do canvas, clicar no selo não arrasta nem move a câmera, e o
 * clique não sobe para abrir o card. Com Alt ele sobe: Alt + clique é o destaque dos cards
 * no mesmo status, e o selo é justamente onde o dev faz isso.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
  status: { type: String, required: true },
})

function open(event) {
  if (event.altKey) return
  event.stopPropagation()
  // Store pego no clique, não no setup: o card do canvas também é montado sem Pinia (testes).
  useJiraActionsStore().openStatus(props.issueKey, event.currentTarget)
}
</script>

<template>
  <button
    type="button"
    class="status-chip nodrag nopan"
    :title="`Status no Jira: ${status} — clique para mover`"
    :aria-label="`Status ${status}. Mover ${issueKey} no Jira`"
    aria-haspopup="dialog"
    @click="open"
  >
    <span class="status-chip__text">{{ status }}</span>
    <ChevronDown :size="10" class="status-chip__caret" aria-hidden="true" />
  </button>
</template>

<style scoped>
/* Só layout e cursor: borda, fundo, cor e tamanho de letra são de quem usa o selo. */
.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;
}

/* Anel em vez de trocar cor: fundo e borda são do selo de quem usa. */
.status-chip:hover {
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring);
}

.status-chip__text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-chip__caret {
  flex-shrink: 0;
  opacity: 0.55;
  transition: opacity var(--duration-fast);
}

.status-chip:hover .status-chip__caret,
.status-chip:focus-visible .status-chip__caret {
  opacity: 1;
}
</style>
