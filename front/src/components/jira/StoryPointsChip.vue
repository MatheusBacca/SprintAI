<script setup>
import { computed } from 'vue'
import { useJiraActionsStore } from '@/stores/jiraActions'

/**
 * "N SP" que abre o editor de Story Points. Como o `StatusChip`, a aparência é de quem
 * usa; sem pontos, mostra o `placeholder` (o painel da tarefa usa para dar onde clicar).
 * `suffix: false` é para onde o número aparece sozinho, como a timeline da Home.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
  points: { type: Number, default: null },
  placeholder: { type: String, default: 'sem SP' },
  suffix: { type: Boolean, default: true },
})

const label = computed(() => {
  if (props.points == null) return props.placeholder
  return props.suffix ? `${props.points} SP` : String(props.points)
})

// Com Alt o clique sobe para o card (destaque de status), como no selo de status.
function open(event) {
  if (event.altKey) return
  event.stopPropagation()
  useJiraActionsStore().openPoints(props.issueKey, event.currentTarget, props.points)
}
</script>

<template>
  <button
    type="button"
    class="points-chip nodrag nopan"
    :data-empty="points == null || null"
    :title="points == null ? 'Sem Story Points — clique para definir' : 'Story Points — clique para alterar'"
    :aria-label="points == null ? `Definir os Story Points de ${issueKey}` : `${points} Story Points. Alterar em ${issueKey}`"
    aria-haspopup="dialog"
    @click="open"
  >
    {{ label }}
  </button>
</template>

<style scoped>
.points-chip {
  cursor: pointer;
}

.points-chip:hover {
  box-shadow: inset 0 0 0 1px var(--color-primary);
}

/* Sem valor: o convite a preencher não pode pesar como um valor de verdade. */
.points-chip[data-empty] {
  font-weight: 500;
  font-style: italic;
  opacity: 0.8;
}
</style>
