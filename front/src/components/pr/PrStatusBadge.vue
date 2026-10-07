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
import ReviewerFaces from './ReviewerFaces.vue'
import { REVIEW_PERSON_LABEL, REVIEW_STATUSES, approvalsLabel, prStatusMeta } from '@/constants/prStatus'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Badge do status de PR. Com PR por trás, leva ao Bitbucket: um PR (`href`, ou um só em
 * `links`) vira link direto; vários abrem a lista para escolher. "Sem PR" e "Branch sem
 * PR" continuam só rótulo — não há PR para abrir.
 *
 * Com a review andando (`review` do back), o rótulo vira a foto de cada revisor, pintada com
 * o estado dele — verde para quem aprovou, amarelo para ajuste pedido e ainda sem correção,
 * neutro para quem falta revisar. As fotos tomaram o lugar da barra do andamento e do "N/X",
 * na mesma ordem; a contagem por extenso fica no title, com o status (que segue também na
 * borda e no ícone).
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
  /** `review` do back: aprovações, revisores, ajustes pendentes, o que a regra pede e quem revisa. */
  review: { type: Object, default: null },
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

const progress = computed(() => {
  const review = props.review
  if (!review?.reviewers || !REVIEW_STATUSES.has(props.status)) return null
  const approvals = Math.min(review.approvals, review.reviewers)
  const changes = Math.min(review.changes_requested, review.reviewers - approvals)
  return {
    ...review,
    people: review.people ?? [],
    label: approvalsLabel(review),
    short: `${review.approvals}/${review.reviewers}`,
    missing: Math.max(0, review.required - approvals),
    changes,
  }
})

const title = computed(() => {
  const parts = [meta.value.label]
  const p = progress.value
  if (p) {
    parts.push(p.label)
    // As fotos não têm nome à vista: quem é quem fica aqui.
    if (p.people.length) parts.push(p.people.map((r) => `${r.name ?? 'Revisor'} ${REVIEW_PERSON_LABEL[r.state] ?? r.state}`).join(', '))
    if (p.changes) parts.push(p.changes === 1 ? '1 pedido de ajuste' : `${p.changes} pedidos de ajuste`)
    if (props.status !== 'aprovada' && p.missing) {
      parts.push(p.missing === 1 ? 'falta 1 aprovação' : `faltam ${p.missing} aprovações`)
    }
  }
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
    :class="[`pr-badge--${size}`, { 'pr-badge--action nodrag nopan': tag !== 'span', 'pr-badge--review': progress }]"
    :style="{ '--badge-color': meta.color }"
    :title="title"
    :data-status="status"
    @click="onClick"
  >
    <component :is="ICONS[meta.icon]" :size="size === 'sm' ? 12 : 14" aria-hidden="true" />
    <template v-if="progress">
      <ReviewerFaces v-if="progress.people.length" :people="progress.people" :size="size === 'sm' ? 15 : 17" />
      <!-- Review sem a lista de quem revisa (resposta antiga em cache): fica a contagem. -->
      <span v-else>{{ progress.short }}</span>
    </template>
    <span v-else>{{ meta.label }}</span>
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
