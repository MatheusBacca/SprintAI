<script setup>
import { CheckCheck } from 'lucide-vue-next'
import { useJiraActionsStore } from '@/stores/jiraActions'

/**
 * "Concluir" do card e do painel da tarefa: abre o plano no painel único do AppShell — o que
 * o repo da tarefa faz no Concluir (Configurações › Concluir), com os avisos — e nada roda
 * antes da confirmação lá. Como os outros chips, não arrasta o canvas nem abre o card; com
 * Alt, o clique sobe para o destaque de status.
 *
 * `pulse` é para o card do canvas: a sombra pulsante do card em desenvolvimento, na cor do
 * botão e em escala de botão — tarefa apta a concluir também é trabalho na mão do dev agora.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
  compact: { type: Boolean, default: false },
  pulse: { type: Boolean, default: false },
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
    :class="{ 'conclude-btn--compact': compact, 'conclude-btn--pulse': pulse }"
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

/* A sombra do `.node--pulse` do card, reduzida: com o halo do tamanho do do card, o botão
   virava uma mancha no rodapé. Num pseudo-elemento para não brigar com o anel do hover; o
   `isolation` segura o z-index -1 dentro do botão — sem ele, o halo ia para trás da
   superfície do card e sumia. */
.conclude-btn--pulse {
  --pulse: var(--color-success);

  position: relative;
  isolation: isolate;
}

.conclude-btn--pulse::after {
  content: '';
  position: absolute;
  inset: -1px;
  z-index: -1;
  border-radius: inherit;
  pointer-events: none;
  animation: conclude-pulse 1.8s ease-in-out infinite;
}

@keyframes conclude-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 1px color-mix(in srgb, var(--pulse) 45%, transparent),
      0 0 3px 0 color-mix(in srgb, var(--pulse) 25%, transparent);
  }

  50% {
    box-shadow:
      0 0 0 2.5px color-mix(in srgb, var(--pulse) 30%, transparent),
      0 0 7px 1px color-mix(in srgb, var(--pulse) 35%, transparent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .conclude-btn--pulse::after {
    animation: none;
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--pulse) 40%, transparent);
  }
}
</style>
