<script setup>
import { ExternalLink } from 'lucide-vue-next'
import StatusChip from '@/components/jira/StatusChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'

defineProps({
  item: { type: Object, required: true },
})
const emit = defineEmits(['open'])
</script>

<template>
  <li class="ref" :class="{ 'ref--done': item.status_category === 'done' }">
    <button
      v-if="item.in_mirror"
      type="button"
      class="ref__key"
      :title="`Abrir ${item.key} no painel`"
      @click="emit('open', item.key)"
    >
      {{ item.key }}
    </button>
    <a v-else-if="item.url" class="ref__key ref__key--external" :href="item.url" target="_blank" rel="noopener noreferrer" title="Fora do espelho local — abrir no Jira">
      {{ item.key }} <ExternalLink :size="11" />
    </a>
    <span v-else class="ref__key ref__key--external">{{ item.key }}</span>

    <span class="ref__summary" :title="item.summary">{{ item.summary || '—' }}</span>
    <!-- Fora do espelho, o status é o que o link trouxe: não dá para mover daqui. -->
    <StatusChip v-if="item.status && item.in_mirror" class="ref__status ref__status--action" :issue-key="item.key" :status="item.status" />
    <span v-else-if="item.status" class="ref__status">{{ item.status }}</span>
    <PrStatusBadge
      v-if="item.pr"
      :status="item.pr.status"
      :pr-count="item.pr.pr_count"
      :build-failed="item.pr.build_failed"
      :links="item.pr.links ?? []"
      :issue-key="item.key"
      size="sm"
    />
  </li>
</template>

<style scoped>
.ref {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  padding: 6px 0;
  font-size: var(--text-sm);
}

.ref + .ref {
  border-top: 1px solid var(--color-border);
}

.ref__key {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
  color: var(--color-primary);
  white-space: nowrap;
}

.ref__key--external {
  color: var(--color-text-secondary);
}

.ref__summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.ref--done .ref__summary {
  color: var(--color-text-muted);
  text-decoration: line-through;
}

.ref__status {
  flex-shrink: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.ref__status--action {
  max-width: 160px;
  padding: 1px 6px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
  background: none;
}

.ref__status--action:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
