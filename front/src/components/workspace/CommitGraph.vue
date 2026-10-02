<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, Cloud, FolderGit2, Tag } from 'lucide-vue-next'
import IssueKeyChip from './IssueKeyChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { labelsBySha, laneColor, layoutGraph } from '@/utils/commitGraph'
import { formatRelative } from '@/utils/time'

/**
 * Lista de commits com as pistas das branches à esquerda (o grafo do gitk). Só as linhas
 * à vista são desenhadas: o `--all` de um repo grande passa de mil commits por página
 * somando as que o dev carrega. Quem usa troca a `key` ao trocar de repo — a rolagem
 * volta ao topo junto.
 */
const props = defineProps({
  commits: { type: Array, required: true },
  refs: { type: Array, required: true },
  worktrees: { type: Array, default: () => [] },
  selectedSha: { type: String, default: null },
  /** Chaves do card aberto: as linhas e etiquetas delas ganham destaque. */
  highlightKeys: { type: Array, default: () => [] },
  hasMore: { type: Boolean, default: false },
  loadingMore: { type: Boolean, default: false },
  /** `{ 'WAI-1': { status, status_label } }` — a cor de cada chave. */
  issueStatus: { type: Object, default: () => ({}) },
  /** Commits que casam com a busca: ficam marcados no grafo. */
  matchShas: { type: Array, default: () => [] },
  /** `{ sha, at }` — rolar até o commit (clique numa branch ou num resultado da busca). */
  scrollTo: { type: Object, default: null },
})
const emit = defineEmits(['select', 'open-issue', 'load-more'])

const ROW = 30
const LANE = 14
const MAX_LANES = 20
const OVERSCAN = 12
const MID = ROW / 2

const layout = computed(() => layoutGraph(props.commits))
const labels = computed(() => labelsBySha(props.refs))
const gutter = computed(() => Math.min(Math.max(layout.value.width, 1), MAX_LANES) * LANE + 10)
const mainPath = computed(() => props.worktrees.find((w) => w.is_main)?.path ?? null)
const highlight = computed(() => new Set(props.highlightKeys))
const matches = computed(() => new Set(props.matchShas))

const x = (lane) => 8 + lane * LANE

// A cor das pistas vai por `style`, não pelos atributos `stroke`/`fill`: `var()` em atributo
// de apresentação do SVG não é garantido, e a cor precisa virar com o tema.

function paths(row) {
  const lines = []
  for (const lane of row.through) {
    if (lane < MAX_LANES) lines.push({ d: `M${x(lane)} 0V${ROW}`, color: laneColor(lane) })
  }
  for (const lane of row.incoming) {
    if (lane >= MAX_LANES) continue
    const d =
      lane === row.lane
        ? `M${x(lane)} 0V${MID}`
        : `M${x(lane)} 0C${x(lane)} ${MID * 0.6} ${x(row.lane)} ${MID * 0.4} ${x(row.lane)} ${MID}`
    lines.push({ d, color: laneColor(lane) })
  }
  for (const lane of row.outgoing) {
    if (lane >= MAX_LANES) continue
    const d =
      lane === row.lane
        ? `M${x(lane)} ${MID}V${ROW}`
        : `M${x(row.lane)} ${MID}C${x(row.lane)} ${MID + MID * 0.6} ${x(lane)} ${MID + MID * 0.4} ${x(lane)} ${ROW}`
    lines.push({ d, color: laneColor(lane) })
  }
  return lines
}

// --- Janela à vista -------------------------------------------------------------------------

const scroller = ref(null)
const scrollTop = ref(0)
const viewport = ref(600)
let observer = null

function onScroll() {
  const el = scroller.value
  if (!el) return
  scrollTop.value = el.scrollTop
  // Chegando no fim da página carregada, pede a próxima.
  if (props.hasMore && !props.loadingMore && el.scrollTop + el.clientHeight > el.scrollHeight - ROW * 8) {
    emit('load-more')
  }
}

onMounted(() => {
  const el = scroller.value
  if (!el) return
  viewport.value = el.clientHeight || 600
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => (viewport.value = el.clientHeight || 600))
    observer.observe(el)
  }
})
onBeforeUnmount(() => observer?.disconnect())

// Pedido de rolagem: o commit vai para um terço da altura, onde o olho já está.
watch(
  () => props.scrollTo,
  (target) => {
    const el = scroller.value
    if (!target || !el) return
    const index = props.commits.findIndex((c) => c.sha === target.sha)
    if (index === -1) return
    el.scrollTop = Math.max(0, index * ROW - viewport.value / 3)
    scrollTop.value = el.scrollTop
  },
)

const range = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / ROW) - OVERSCAN)
  const end = Math.min(props.commits.length, Math.ceil((scrollTop.value + viewport.value) / ROW) + OVERSCAN)
  return { start, end }
})

const visible = computed(() => {
  const { start, end } = range.value
  const rows = layout.value.rows
  return props.commits.slice(start, end).map((commit, i) => ({ commit, row: rows[start + i], index: start + i }))
})

/** Alterações não commitadas, uma linha por worktree com mudança (o "Work in progress"). */
const pending = computed(() =>
  props.worktrees.filter((w) => w.changes && w.changes.changed + w.changes.untracked + w.changes.conflicted > 0),
)

function pendingText(changes) {
  const parts = []
  if (changes.changed) parts.push(`${changes.changed} alterado(s)`)
  if (changes.untracked) parts.push(`${changes.untracked} não rastreado(s)`)
  if (changes.conflicted) parts.push(`${changes.conflicted} em conflito`)
  return parts.join(' · ')
}

function isHighlighted(commit) {
  return commit.issue_keys.some((k) => highlight.value.has(k))
}

function labelHighlighted(label) {
  return label.issue_keys?.some((k) => highlight.value.has(k))
}

function worktreeTitle(label) {
  return label.worktree === mainPath.value ? 'Aberta no clone principal' : `Aberta na worktree ${label.worktree}`
}
</script>

<template>
  <div class="graph">
    <ul v-if="pending.length" class="graph__pending" aria-label="Alterações não commitadas">
      <li v-for="wt in pending" :key="wt.path" class="pending" :title="wt.path">
        <span class="pending__dot" aria-hidden="true" />
        <strong>Alterações não commitadas</strong>
        <span class="pending__counts">{{ pendingText(wt.changes) }}</span>
        <span class="pending__where">{{ wt.branch ?? 'HEAD destacado' }}<template v-if="!wt.is_main"> · worktree</template></span>
      </li>
    </ul>

    <div ref="scroller" class="graph__scroll" @scroll.passive="onScroll">
      <div class="graph__inner" :style="{ height: `${commits.length * ROW}px` }">
        <div
          v-for="{ commit, row, index } in visible"
          :key="commit.sha"
          class="commit"
          :class="{
            'commit--selected': commit.sha === selectedSha,
            'commit--highlight': isHighlighted(commit),
            'commit--merge': commit.parents.length > 1,
            'commit--match': matches.has(commit.sha),
            'commit--boundary': commit.boundary,
          }"
          :style="{ top: `${index * ROW}px`, height: `${ROW}px` }"
          :data-sha="commit.sha"
          role="button"
          tabindex="0"
          @click="emit('select', commit.sha)"
          @keydown.enter="emit('select', commit.sha)"
        >
          <svg class="commit__lanes" :width="gutter" :height="ROW" aria-hidden="true">
            <path v-for="(line, i) in paths(row)" :key="i" :d="line.d" :style="{ stroke: line.color }" class="commit__line" />
            <circle
              v-if="row.lane < MAX_LANES"
              :cx="x(row.lane)"
              :cy="MID"
              :r="commit.parents.length > 1 ? 3 : 4"
              :style="commit.boundary ? { fill: 'var(--color-surface)', stroke: laneColor(row.lane) } : { fill: laneColor(row.lane) }"
              class="commit__node"
            />
          </svg>

          <span v-if="labels[commit.sha]" class="commit__labels">
            <span
              v-for="label in labels[commit.sha]"
              :key="`${label.kind}:${label.name}`"
              class="label"
              :class="[`label--${label.kind}`, { 'label--feature': label.in_feature, 'label--head': label.is_head, 'label--marked': labelHighlighted(label) }]"
              :style="{ '--lane': laneColor(row.lane) }"
              :title="label.upstream ? `${label.name} → ${label.upstream}` : label.name"
            >
              <Tag v-if="label.kind === 'tag'" :size="10" />
              <span v-if="label.is_head" class="label__head">HEAD</span>
              <span class="label__name">{{ label.name }}</span>
              <Cloud v-if="label.synced" :size="10" class="label__synced" aria-label="igual ao origin" />
              <span v-if="label.ahead" class="label__track" :title="`${label.ahead} commit(s) para enviar`"><ArrowUp :size="9" />{{ label.ahead }}</span>
              <span v-if="label.behind" class="label__track" :title="`${label.behind} commit(s) para trazer`"><ArrowDown :size="9" />{{ label.behind }}</span>
              <span v-if="label.gone" class="label__gone" title="A branch foi apagada no Bitbucket">apagada no remoto</span>
              <span v-if="label.worktree && label.worktree !== mainPath" class="label__wt" :title="worktreeTitle(label)">
                <FolderGit2 :size="10" />
              </span>
            </span>
            <template v-for="label in labels[commit.sha]" :key="`pr:${label.kind}:${label.name}`">
              <PrStatusBadge
                v-if="label.pull_requests?.length && label.kind === 'local'"
                :status="label.pull_requests[0].status"
                :pr-count="label.pull_requests.length"
                :links="label.pull_requests"
                :review="label.pull_requests[0].review"
                size="sm"
              />
            </template>
          </span>

          <span v-if="commit.boundary" class="commit__base" title="Ponto da base em que a feature se apoia — não é commit da feature">base</span>
          <span class="commit__subject" :title="commit.subject">{{ commit.subject }}</span>
          <IssueKeyChip
            v-for="key in commit.issue_keys"
            :key="key"
            :issue-key="key"
            :status="issueStatus[key]"
            @open="emit('open-issue', $event)"
          />
          <span class="commit__author">{{ commit.author }}</span>
          <span class="commit__date" :title="commit.committed_at">{{ formatRelative(commit.committed_at) }}</span>
          <code class="commit__sha">{{ commit.sha.slice(0, 7) }}</code>
        </div>
      </div>
      <p v-if="loadingMore" class="graph__more muted">Carregando mais commits…</p>
      <button v-else-if="hasMore" type="button" class="graph__more btn btn--secondary" @click="emit('load-more')">Carregar mais</button>
    </div>
  </div>
</template>

<style scoped>
.graph {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.graph__pending {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  list-style: none;
  border-bottom: 1px solid var(--color-border);
}

.pending {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.pending__dot {
  width: 9px;
  height: 9px;
  border: 2px dashed var(--color-warning);
  border-radius: 50%;
}

.pending strong {
  color: var(--color-text);
  font-weight: 600;
}

.pending__where {
  margin-left: auto;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}

.graph__scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.graph__inner {
  position: relative;
  min-width: 720px;
}

.commit {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding-right: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.commit:hover {
  background: var(--color-surface-hover);
}

.commit--selected {
  background: var(--color-primary-soft);
}

.commit--highlight .commit__subject {
  color: var(--color-primary);
  font-weight: 600;
}

.commit--match {
  box-shadow: inset 3px 0 0 var(--color-primary);
}

.commit--match .commit__subject {
  background: var(--color-mark);
}

.commit--boundary .commit__subject {
  color: var(--color-text-muted);
}

.commit__base {
  flex-shrink: 0;
  padding: 0 5px;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: 10px;
}

.commit--merge .commit__subject {
  color: var(--color-text-muted);
}

.commit__lanes {
  flex-shrink: 0;
  overflow: visible;
}

.commit__line {
  fill: none;
  stroke-width: 2;
}

.commit__node {
  stroke: var(--color-surface);
  stroke-width: 2;
}

.commit__labels {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 50%;
  overflow: hidden;
}

.label {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  max-width: 260px;
  padding: 1px 6px;
  border: 1px solid var(--lane);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--lane) 14%, var(--color-surface));
  color: var(--color-text);
  font-size: 11px;
  line-height: 16px;
}

.label--remote {
  background: transparent;
  color: var(--color-text-secondary);
  border-style: dashed;
}

.label--tag {
  border-color: var(--git-tag-border);
  background: var(--git-tag-bg);
  color: var(--git-tag-text);
  font-weight: 600;
}

.label--feature {
  background: color-mix(in srgb, var(--lane) 30%, var(--color-surface));
  font-weight: 600;
}

.label--marked {
  box-shadow: 0 0 0 2px var(--color-primary-focus-ring);
}

.label__head {
  font-weight: 700;
  color: var(--color-primary);
}

.label__name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.label__track {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-secondary);
}

.label__gone {
  color: var(--color-warning-text);
}

.label__wt {
  display: inline-flex;
}

.label__synced {
  color: var(--color-text-muted);
}

.commit__subject {
  flex: 1;
  min-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text);
}


.commit__author {
  flex-shrink: 0;
  width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.commit__date {
  flex-shrink: 0;
  width: 90px;
  color: var(--color-text-muted);
}

.commit__sha {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.graph__more {
  display: block;
  margin: var(--space-3) auto;
  font-size: var(--text-xs);
  text-align: center;
}
</style>
