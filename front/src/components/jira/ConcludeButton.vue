<script setup>
import { CheckCheck } from 'lucide-vue-next'
import { useJiraActionsStore } from '@/stores/jiraActions'

/**
 * "Concluir" do card e do painel da tarefa: abre o plano no painel único do AppShell — o que
 * o repo da tarefa faz no Concluir (Configurações › Concluir), com os avisos — e nada roda
 * antes da confirmação lá. Como os outros chips, não arrasta o canvas nem abre o card; com
 * Alt, o clique sobe para o destaque de status.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
  compact: { type: Boolean, default: false },
})

function open(event) {
  if (event.altKey) return
  event.stopPropagation()
  useJiraActionsStore().openConclude(props.issueKey, event.currentTarget)
}
</script>

<template>
  <button
    type="button"
    class="conclude-btn nodrag nopan"
    :class="{ 'conclude-btn--compact': compact }"
    :title="`Concluir ${issueKey}: ver o que o repo faz (merge, status no Jira) e confirmar`"
    :aria-label="`Concluir ${issueKey}`"
    aria-haspopup="dialog"
    @click="open"
  >
    <CheckCheck :size="12" />
    <span>Concluir</span>
  </button>
</template>

<style scoped>
.conclude-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 8px;
  border: 1px solid var(--color-success-border);
  border-radius: 999px;
  background: var(--color-success-surface);
  color: var(--color-success-text);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.conclude-btn:hover {
  box-shadow: inset 0 0 0 1px var(--color-success-text);
}

.conclude-btn--compact span {
  display: none;
}
</style>
