<script setup>
import { computed } from 'vue'
import { prStatusMeta } from '@/constants/prStatus'

/**
 * A chave `WAI-XXXX` de um commit ou branch na linha do tempo, na cor do status de PR da
 * tarefa — a mesma do selo do card e do painel (Mergeada roxo, Aprovada verde…). Sem status
 * (a tarefa nem passou pelo back), fica neutra. Clique abre a tarefa.
 */
const props = defineProps({
  issueKey: { type: String, required: true },
  /** `{ status, status_label }` do back (`issue_status`). */
  status: { type: Object, default: null },
})
const emit = defineEmits(['open'])

const color = computed(() => (props.status ? prStatusMeta(props.status.status).color : 'var(--color-text-muted)'))
const title = computed(() =>
  props.status ? `${props.issueKey} · ${props.status.status_label} — abrir a tarefa` : `${props.issueKey} — abrir a tarefa`,
)
</script>

<template>
  <button
    type="button"
    class="key"
    :style="{ '--pr': color }"
    :data-status="status?.status ?? null"
    :title="title"
    @click.stop="emit('open', issueKey)"
  >
    {{ issueKey }}
  </button>
</template>

<style scoped>
.key {
  flex-shrink: 0;
  padding: 0 5px;
  border: 1px solid color-mix(in srgb, var(--pr) 45%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pr) 16%, var(--color-surface));
  color: color-mix(in srgb, var(--pr) 75%, var(--color-text));
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
}

.key:hover {
  border-color: var(--pr);
}
</style>
