<script setup>
import { computed } from 'vue'
import {
  ArrowRightLeft,
  CalendarRange,
  Circle,
  CircleCheck,
  CircleX,
  Flag,
  GitCommitHorizontal,
  GitMerge,
  GitPullRequest,
  GitPullRequestClosed,
  Hash,
  MessageSquare,
  MessageSquareWarning,
  UserRound,
} from 'lucide-vue-next'

import { activityKindMeta } from '@/constants/activityKinds'

/**
 * Ícone colorido do tipo de evento. Só os ícones que os tipos declaram entram aqui —
 * `import * as icons from 'lucide-vue-next'` levaria a biblioteca inteira para o bundle.
 */
const props = defineProps({
  kind: { type: String, required: true },
  size: { type: Number, default: 13 },
})

const ICONS = {
  ArrowRightLeft,
  CalendarRange,
  Circle,
  CircleCheck,
  CircleX,
  Flag,
  GitCommitHorizontal,
  GitMerge,
  GitPullRequest,
  GitPullRequestClosed,
  Hash,
  MessageSquare,
  MessageSquareWarning,
  UserRound,
}

const meta = computed(() => activityKindMeta(props.kind))
const icon = computed(() => ICONS[meta.value.icon] ?? Circle)
</script>

<template>
  <span class="kind" :style="{ color: meta.color }">
    <component :is="icon" :size="size" />
  </span>
</template>

<style scoped>
.kind {
  display: inline-flex;
  flex-shrink: 0;
}
</style>
