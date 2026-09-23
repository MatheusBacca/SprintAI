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
import { useJiraActionsStore } from '@/stores/jiraActions'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Badge do status de PR. Com PR por trás, leva ao Bitbucket: um PR (`href`, ou um só em
 * `links`) vira link direto; vários abrem a lista para escolher. "Sem PR" e "Branch sem
 * PR" continuam só rótulo — não há PR para abrir.
 *
 * O clique não sobe: o badge mora dentro do card do canvas, da linha da Semana e da
 * dependência do painel, e todos abrem a tarefa no clique.
 */
const props = defineProps({
  status: { type: String, required: true },
  prCount: { type: Number, default: 0 },
  buildFailed: { type: Boolean, default: false },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
  /** `links` do back: do PR que decide o status para o resto. */
  links: { type: Array, default: () => [] },
  /** Um PR específico (aba PRs do painel). Vence `links`. */
  href: { type: String, default: null },
  issueKey: { type: String, default: null },
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
const url = computed(() => {
  if (props.href) return safeUrl(props.href)
  return props.links.length === 1 ? safeUrl(props.links[0].url) : null
})
const menu = computed(() => !props.href && props.links.length > 1)

const title = computed(() => {
  const parts = [meta.value.label]
  if (props.prCount > 1) parts.push(`${props.prCount} PRs`)
  if (props.buildFailed) parts.push('build falhando')
  const text = parts.join(' · ')
  if (url.value) return `${text} — abrir no Bitbucket`
  if (menu.value) return `${text} — escolher o PR para abrir no Bitbucket`
  return text
})

const tag = computed(() => (url.value ? 'a' : menu.value ? 'button' : 'span'))
const attrs = computed(() => {
  if (url.value) return { href: url.value, target: '_blank', rel: 'noopener noreferrer' }
  if (menu.value) return { type: 'button', 'aria-haspopup': 'dialog' }
  return {}
})

function onClick(event) {
  if (tag.value === 'span') return
  event.stopPropagation()
  // Store pego no clique: o badge também é montado sem Pinia (testes do canvas).
  if (menu.value) useJiraActionsStore().openPullRequests(props.links, event.currentTarget, props.issueKey)
}
</script>

<template>
  <component
    :is="tag"
    v-bind="attrs"
    class="pr-badge"
    :class="[`pr-badge--${size}`, { 'pr-badge--action nodrag nopan': tag !== 'span' }]"
    :style="{ '--badge-color': meta.color }"
    :title="title"
    :data-status="status"
    @click="onClick"
  >
    <component :is="ICONS[meta.icon]" :size="size === 'sm' ? 12 : 14" aria-hidden="true" />
    <span>{{ meta.label }}</span>
    <span v-if="prCount > 1" class="pr-badge__count">{{ prCount }} PRs</span>
    <TriangleAlert v-if="buildFailed" :size="12" class="pr-badge__build" aria-label="build falhando" />
  </component>
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

.pr-badge--action {
  cursor: pointer;
  text-decoration: none;
  transition: border-color var(--duration-fast), background var(--duration-fast);
}

.pr-badge--action:hover {
  border-color: var(--badge-color);
  background: color-mix(in srgb, var(--badge-color) 22%, var(--color-surface));
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
