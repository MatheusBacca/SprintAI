<script setup>
import { computed } from 'vue'
import {
  CircleCheck,
  CircleDashed,
  FilePen,
  GitBranch,
  GitMerge,
  GitPullRequest,
  GitPullRequestClosed,
  MessageSquareWarning,
  TriangleAlert,
} from 'lucide-vue-next'
import { prStatusMeta } from '@/constants/prStatus'

const props = defineProps({
  status: { type: String, required: true },
  prCount: { type: Number, default: 0 },
  buildFailed: { type: Boolean, default: false },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
})

const ICONS = {
  CircleCheck,
  CircleDashed,
  FilePen,
  GitBranch,
  GitMerge,
  GitPullRequest,
  GitPullRequestClosed,
  MessageSquareWarning,
}

const meta = computed(() => prStatusMeta(props.status))
const title = computed(() => {
  const parts = [meta.value.label]
  if (props.prCount > 1) parts.push(`${props.prCount} PRs`)
  if (props.buildFailed) parts.push('build falhando')
  return parts.join(' · ')
})
</script>

<template>
  <span
    class="pr-badge"
    :class="`pr-badge--${size}`"
    :style="{ '--badge-color': meta.color }"
    :title="title"
    :data-status="status"
  >
    <component :is="ICONS[meta.icon]" :size="size === 'sm' ? 12 : 14" aria-hidden="true" />
    <span>{{ meta.label }}</span>
    <span v-if="prCount > 1" class="pr-badge__count">{{ prCount }} PRs</span>
    <TriangleAlert v-if="buildFailed" :size="12" class="pr-badge__build" aria-label="build falhando" />
  </span>
</template>

<style scoped>
.pr-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid color-mix(in srgb, var(--badge-color) 35%, transparent);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--badge-color) 12%, var(--color-surface));
  color: color-mix(in srgb, var(--badge-color) 80%, var(--color-text));
  font-size: var(--text-xs);
  font-weight: 600;
  line-height: 18px;
  white-space: nowrap;
}

.pr-badge--sm {
  padding: 0 6px;
  font-size: 11px;
}

.pr-badge__count {
  padding-left: 4px;
  border-left: 1px solid color-mix(in srgb, var(--badge-color) 35%, transparent);
  font-weight: 500;
}

.pr-badge__build {
  color: var(--color-error);
}
</style>
