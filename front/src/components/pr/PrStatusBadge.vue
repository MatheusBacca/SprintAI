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
import { REVIEW_STATUSES, approvalsLabel, prStatusMeta } from '@/constants/prStatus'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Badge do status de PR. Com PR por trás, leva ao Bitbucket: um PR (`href`, ou um só em
 * `links`) vira link direto; vários abrem a lista para escolher. "Sem PR" e "Branch sem
 * PR" continuam só rótulo — não há PR para abrir.
 *
 * Com a review andando (`review` do back), o rótulo vira "N/X" à direita de uma barra do
 * andamento: verde para quem aprovou, amarelo para ajuste pedido e ainda sem correção,
 * liso para quem falta revisar. O status continua na borda, no ícone e no title.
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
  /** `review` do back: aprovações, revisores, ajustes pendentes e o que a regra pede. */
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
    label: approvalsLabel(review),
    short: `${review.approvals}/${review.reviewers}`,
    missing: Math.max(0, review.required - approvals),
    changes,
    style: {
      '--review-approved': `${(approvals / review.reviewers) * 100}%`,
      '--review-changes': `${(changes / review.reviewers) * 100}%`,
    },
  }
})

const title = computed(() => {
  const parts = [meta.value.label]
  const p = progress.value
  if (p) {
    parts.push(p.label)
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
    :style="{ '--badge-color': meta.color, ...progress?.style }"
    :title="title"
    :data-status="status"
    @click="onClick"
  >
    <component :is="ICONS[meta.icon]" :size="size === 'sm' ? 12 : 14" aria-hidden="true" />
    <template v-if="progress">
      <span class="pr-badge__bar" aria-hidden="true" />
      <span>{{ progress.short }}</span>
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

/*
 * Barra da review, à esquerda do "N/X" — com o texto por cima dela a leitura sofria.
 * As listras são uma camada só, por cima dos segmentos: nas faixas transparentes aparece
 * a cor do segmento de baixo, nas outras o fundo do trilho. Listrar cada segmento
 * separado quebraria a diagonal na emenda do verde com o amarelo.
 */
.pr-badge__bar {
  --track: color-mix(in srgb, var(--badge-color) 6%, var(--color-surface));
  flex-shrink: 0;
  width: 48px;
  height: 12px;
  border-radius: 3px;
  background:
    repeating-linear-gradient(-45deg, transparent 0 3px, var(--track) 3px 6px),
    linear-gradient(
      90deg,
      var(--pr-approved) 0 var(--review-approved),
      var(--pr-changes) 0 calc(var(--review-approved) + var(--review-changes)),
      var(--track) 0
    );
  /* Contorno por dentro: o trilho vazio continua visível sobre o fundo do badge. */
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--badge-color) 40%, transparent);
}

.pr-badge--sm .pr-badge__bar {
  width: 40px;
  height: 10px;
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
