<script setup>
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight, GitBranch, ListChecks, Milestone } from 'lucide-vue-next'
import StoryPointsChip from '@/components/jira/StoryPointsChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'

/**
 * Timeline no formato da do Jira (Plans): faixa de meses, linha das sprints, marcador
 * de hoje, grupos recolhíveis por pai e uma barra por tarefa, segmentada por status.
 *
 * Sem biblioteca — CSS grid para as linhas, `div` posicionadas em pixels para as barras
 * e um SVG só para as setas de bloqueio (mesmo espírito do `utils/treeLayout.js`).
 * Trabalhar em pixels (e não em %) deixa as curvas do SVG e as barras no mesmo sistema
 * de coordenadas, sem precisar medir o DOM.
 */
const props = defineProps({
  timeline: { type: Object, default: null },
  selectedKey: { type: String, default: null },
})
const emit = defineEmits(['open'])

const LABEL_WIDTH = 340
const ROW_HEIGHT = 30
const MIN_BAR = 6
const DAY_MS = 86_400_000

const collapsed = ref(new Set())
// Timeline recarregada: grupos que sumiram não podem ficar guardados como recolhidos.
watch(
  () => props.timeline,
  (value) => {
    const keys = new Set((value?.groups ?? []).map((g) => g.key ?? '—'))
    collapsed.value = new Set([...collapsed.value].filter((k) => keys.has(k)))
  },
)

const monthFormat = new Intl.DateTimeFormat('pt-BR', { month: 'short' })
const dayFormat = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short' })
const fullFormat = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

const startOfDay = (iso) => new Date(`${iso}T00:00:00`)
const groupId = (group) => group.key ?? '—'

const window_ = computed(() => {
  const t = props.timeline
  if (!t) return null
  const start = startOfDay(t.start)
  // O fim do dia final: uma barra que termina "no dia 18" ocupa o dia 18 inteiro.
  const end = new Date(startOfDay(t.end).getTime() + DAY_MS)
  const days = Math.max(1, Math.round((end - start) / DAY_MS))
  const dayWidth = Math.max(16, Math.min(64, Math.round(980 / days)))
  return { start, end, days, dayWidth, width: days * dayWidth }
})

/** Instante → pixels a partir do início da janela. */
function x(value) {
  const w = window_.value
  if (!w) return 0
  const at = value instanceof Date ? value : new Date(value)
  return Math.max(0, Math.min(w.width, ((at - w.start) / DAY_MS) * w.dayWidth))
}

const days = computed(() => {
  const w = window_.value
  if (!w) return []
  return Array.from({ length: w.days }, (_, index) => {
    const date = new Date(w.start.getTime() + index * DAY_MS)
    return {
      key: date.toISOString().slice(0, 10),
      date,
      label: String(date.getDate()),
      weekend: date.getDay() === 0 || date.getDay() === 6,
      left: index * w.dayWidth,
      width: w.dayWidth,
    }
  })
})

const months = computed(() => {
  const groups = []
  for (const day of days.value) {
    const label = monthFormat.format(day.date).replace('.', '').toUpperCase()
    const last = groups.at(-1)
    if (last && last.label === label) last.width += day.width
    else groups.push({ label, left: day.left, width: day.width })
  }
  return groups
})

const sprintChips = computed(() =>
  (props.timeline?.sprints ?? [])
    .filter((sprint) => sprint.start && sprint.end)
    .map((sprint) => {
      const left = x(startOfDay(sprint.start))
      const right = x(new Date(startOfDay(sprint.end).getTime() + DAY_MS))
      return { ...sprint, left, width: Math.max(MIN_BAR, right - left) }
    }),
)

const todayLeft = computed(() => (props.timeline ? x(new Date()) : 0))
const todayLabel = computed(() => (props.timeline ? dayFormat.format(new Date()) : ''))

function bar(issue) {
  const left = x(issue.start)
  const right = x(issue.end)
  const width = Math.max(MIN_BAR, right - left)
  return {
    left,
    width,
    segments: (issue.segments ?? []).map((segment) => ({
      ...segment,
      left: x(segment.start) - left,
      width: Math.max(2, x(segment.end) - x(segment.start)),
      title: `${segment.status}: ${fullFormat.format(new Date(segment.start))} → ${fullFormat.format(new Date(segment.end))}`,
    })),
    // Trecho a partir de hoje: é projeção, não história.
    projection: issue.projected && right > todayLeft.value
      ? { left: Math.max(0, todayLeft.value - left), width: right - Math.max(left, todayLeft.value) }
      : null,
  }
}

/** Lista achatada (grupo + tarefas visíveis) — é ela que define o y de cada linha. */
const rows = computed(() => {
  const result = []
  for (const group of props.timeline?.groups ?? []) {
    const id = groupId(group)
    const isCollapsed = collapsed.value.has(id)
    const starts = group.issues.map((i) => x(i.start))
    const ends = group.issues.map((i) => x(i.end))
    const left = Math.min(...starts, Infinity)
    const right = Math.max(...ends, 0)
    result.push({
      type: 'group',
      id,
      group,
      collapsed: isCollapsed,
      bar: group.issues.length ? { left, width: Math.max(MIN_BAR, right - left) } : null,
    })
    if (isCollapsed) continue
    for (const issue of group.issues) {
      result.push({ type: 'issue', id: issue.key, issue, bar: bar(issue) })
    }
  }
  return result.map((row, index) => ({ ...row, y: index * ROW_HEIGHT }))
})

const rowByKey = computed(() => new Map(rows.value.map((row) => [row.id, row])))

/** Setas "bloqueia": só entre linhas visíveis (grupo recolhido esconde as duas pontas). */
const links = computed(() =>
  (props.timeline?.links ?? [])
    .map((link) => ({ link, from: rowByKey.value.get(link.source), to: rowByKey.value.get(link.target) }))
    .filter(({ from, to }) => from?.bar && to?.bar)
    .map(({ link, from, to }) => {
      const x1 = from.bar.left + from.bar.width
      const y1 = from.y + ROW_HEIGHT / 2
      const x2 = to.bar.left
      const y2 = to.y + ROW_HEIGHT / 2
      const bend = Math.max(14, Math.min(40, Math.abs(x2 - x1) / 2))
      return {
        key: `${link.source}->${link.target}`,
        d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`,
        title: `${link.source} bloqueia ${link.target}`,
        tip: { x: x2, y: y2 },
      }
    }),
)

const height = computed(() => rows.value.length * ROW_HEIGHT)

function toggle(id) {
  const next = new Set(collapsed.value)
  if (!next.delete(id)) next.add(id)
  collapsed.value = next
}

const percent = (value) => `${Math.round((value ?? 0) * 100)}%`
</script>

<template>
  <article class="card tl">
    <header class="tl__head">
      <h2 class="tl__title"><Milestone :size="16" /> Timeline</h2>
      <span v-if="timeline" class="tl__today-label">hoje · {{ todayLabel }}</span>
      <slot name="actions" />
    </header>

    <p v-if="!timeline" class="tl__empty">Carregando a timeline…</p>
    <p v-else-if="!rows.length" class="tl__empty">
      Nenhuma tarefa sua nas sprints ativas. Assim que uma tarefa entrar na sprint, a linha aparece aqui.
    </p>

    <div v-else class="tl__scroll">
      <div
        class="tl__inner"
        :style="{
          '--label-w': `${LABEL_WIDTH}px`,
          '--track-w': `${window_.width}px`,
          '--row-h': `${ROW_HEIGHT}px`,
        }"
      >
        <!-- Fundo: fins de semana, marcador de hoje -->
        <div class="tl__overlay" aria-hidden="true">
          <div
            v-for="day in days"
            :key="day.key"
            class="tl__day"
            :data-weekend="day.weekend || null"
            :style="{ left: `${day.left}px`, width: `${day.width}px` }"
          />
          <div class="tl__today" :style="{ left: `${todayLeft}px` }" />
        </div>

        <div class="tl__grid">
          <div class="tl__cell tl__cell--label tl__cell--head">Meses</div>
          <div class="tl__cell tl__cell--track tl__cell--head">
            <span v-for="month in months" :key="month.left" class="tl__month" :style="{ left: `${month.left}px`, width: `${month.width}px` }">
              {{ month.label }}
            </span>
          </div>

          <div class="tl__cell tl__cell--label tl__cell--days">Dias</div>
          <div class="tl__cell tl__cell--track tl__cell--days">
            <span v-for="day in days" :key="day.key" class="tl__daynum" :style="{ left: `${day.left}px`, width: `${day.width}px` }">
              {{ day.label }}
            </span>
          </div>

          <div class="tl__cell tl__cell--label">Sprints</div>
          <div class="tl__cell tl__cell--track tl__cell--sprints">
            <span
              v-for="sprint in sprintChips"
              :key="sprint.id"
              class="tl__sprint"
              :data-current="sprint.current || null"
              :data-overdue="sprint.overdue_active || null"
              :style="{ left: `${sprint.left}px`, width: `${sprint.width}px` }"
              :title="sprint.overdue_active ? `${sprint.name} — venceu e continua ativa` : sprint.name"
            >
              {{ sprint.name }}
            </span>
          </div>
        </div>

        <div class="tl__rows" :style="{ height: `${height}px` }">
          <svg class="tl__links" :width="window_.width" :height="height" :style="{ left: `${LABEL_WIDTH}px` }" aria-hidden="true">
            <path v-for="link in links" :key="link.key" :d="link.d" class="tl__link">
              <title>{{ link.title }}</title>
            </path>
            <circle v-for="link in links" :key="`${link.key}-tip`" :cx="link.tip.x" :cy="link.tip.y" r="2.5" class="tl__link-tip" />
          </svg>

          <div
            v-for="row in rows"
            :key="row.id"
            class="tl__row"
            :data-type="row.type"
            :class="{ 'tl__row--selected': row.type === 'issue' && row.issue.key === selectedKey }"
            :style="{ top: `${row.y}px` }"
          >
            <!-- Coluna fixa: pai recolhível ou tarefa -->
            <div class="tl__cell tl__cell--label">
              <template v-if="row.type === 'group'">
                <button type="button" class="tl__toggle" :aria-expanded="!row.collapsed" @click="toggle(row.id)">
                  <ChevronRight v-if="row.collapsed" :size="14" />
                  <ChevronDown v-else :size="14" />
                </button>
                <button
                  v-if="row.group.key"
                  type="button"
                  class="tl__name tl__name--group"
                  :title="row.group.summary"
                  @click="emit('open', row.group.key)"
                >
                  <strong class="tl__key">{{ row.group.key }}</strong>
                  <span class="tl__summary">{{ row.group.summary }}</span>
                </button>
                <span v-else class="tl__name tl__name--group"><span class="tl__summary">{{ row.group.summary }}</span></span>
                <span class="tl__count">{{ row.group.issues.length }}</span>
                <span class="tl__progress" :title="`Progresso do grupo: ${percent(row.group.progress)}`">
                  <span class="tl__progress-fill" :style="{ width: percent(row.group.progress) }" />
                </span>
              </template>

              <template v-else>
                <button
                  type="button"
                  class="tl__name"
                  :title="row.issue.summary"
                  @click="emit('open', row.issue.key)"
                >
                  <strong class="tl__key" :data-done="row.issue.status_category === 'done' || null">{{ row.issue.key }}</strong>
                  <span class="tl__summary">{{ row.issue.summary }}</span>
                </button>
                <span class="tl__status" :style="{ background: row.issue.progress.stage_color ?? 'var(--color-surface-muted)' }">
                  {{ row.issue.progress.stage_label ?? row.issue.status }}
                </span>
                <StoryPointsChip
                  v-if="row.issue.story_points != null"
                  class="tl__sp"
                  :issue-key="row.issue.key"
                  :points="row.issue.story_points"
                  :suffix="false"
                />
                <PrStatusBadge
                  v-if="row.issue.pr"
                  :status="row.issue.pr.status"
                  :pr-count="row.issue.pr.pr_count"
                  :build-failed="row.issue.pr.build_failed"
                  :links="row.issue.pr.links ?? []"
                  :issue-key="row.issue.key"
                  size="sm"
                />
              </template>
            </div>

            <!-- Faixa de tempo -->
            <div class="tl__cell tl__cell--track">
              <div
                v-if="row.type === 'group' && row.bar"
                class="tl__bar tl__bar--group"
                :style="{ left: `${row.bar.left}px`, width: `${row.bar.width}px` }"
              >
                <span class="tl__bar-fill" :style="{ width: percent(row.group.progress) }" />
              </div>

              <div
                v-else-if="row.type === 'issue'"
                class="tl__bar"
                :data-projected="row.issue.projected || null"
                :style="{ left: `${row.bar.left}px`, width: `${row.bar.width}px` }"
              >
                <span
                  v-for="(segment, index) in row.bar.segments"
                  :key="index"
                  class="tl__segment"
                  :style="{
                    left: `${segment.left}px`,
                    width: `${segment.width}px`,
                    background: segment.color ?? 'var(--pr-branch)',
                  }"
                  :title="segment.title"
                />
                <span
                  v-if="row.bar.projection"
                  class="tl__projection"
                  :style="{ left: `${row.bar.projection.left}px`, width: `${row.bar.projection.width}px` }"
                  title="Projeção até o fim da sprint — a tarefa ainda não foi concluída"
                />
                <GitBranch v-if="!row.issue.started" :size="11" class="tl__not-started" title="Ainda não saiu da análise" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <footer v-if="timeline && rows.length" class="tl__legend">
      <ListChecks :size="12" />
      <span>barra segmentada pelo status · faixa listrada é projeção até o fim da sprint · linha laranja é hoje</span>
    </footer>
  </article>
</template>

<style scoped>
.tl {
  padding: var(--space-4);
  min-width: 0;
}

.tl__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.tl__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.tl__title svg {
  color: var(--color-primary);
}

.tl__today-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-warning);
}

.tl__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* Rolagem horizontal própria: a página não rola junto. */
.tl__scroll {
  overflow-x: auto;
  overflow-y: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.tl__inner {
  position: relative;
  width: calc(var(--label-w) + var(--track-w));
  min-width: 100%;
}

.tl__overlay {
  position: absolute;
  top: 0;
  bottom: 0;
  left: var(--label-w);
  width: var(--track-w);
  pointer-events: none;
}

.tl__day {
  position: absolute;
  top: 0;
  bottom: 0;
  border-right: 1px solid var(--color-border);
}

.tl__day[data-weekend] {
  background: var(--color-surface-muted);
}

.tl__today {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--color-warning);
  transform: translateX(-1px);
  z-index: 1;
}

.tl__grid,
.tl__row {
  display: grid;
  grid-template-columns: var(--label-w) var(--track-w);
}

.tl__cell {
  position: relative;
  min-width: 0;
}

.tl__cell--label {
  position: sticky;
  left: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 var(--space-2);
  border-right: 1px solid var(--color-border-strong);
  background: var(--color-surface);
}

.tl__cell--head,
.tl__cell--days {
  height: 22px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.tl__cell--days {
  height: 18px;
}

.tl__cell--sprints {
  height: 26px;
}

.tl__grid .tl__cell--label {
  letter-spacing: 0.4px;
  text-transform: uppercase;
}

.tl__month,
.tl__daynum,
.tl__sprint {
  position: absolute;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
}

.tl__month {
  justify-content: center;
  border-left: 1px solid var(--color-border-strong);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: var(--color-text-secondary);
}

.tl__daynum {
  justify-content: center;
  font-size: 10px;
  color: var(--color-text-muted);
}

.tl__sprint {
  top: 3px;
  bottom: 3px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tl__sprint[data-current] {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.tl__sprint[data-overdue] {
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
}

.tl__rows {
  position: relative;
}

.tl__row {
  position: absolute;
  left: 0;
  right: 0;
  height: var(--row-h);
}

.tl__row[data-type='group'] .tl__cell--label {
  background: var(--color-surface-muted);
}

.tl__row[data-type='group'] {
  border-top: 1px solid var(--color-border);
}

.tl__row--selected .tl__cell--label {
  background: var(--color-primary-soft);
}

.tl__toggle {
  display: flex;
  flex-shrink: 0;
  padding: 2px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-secondary);
}

.tl__toggle:hover {
  background: var(--color-surface-hover);
}

.tl__name {
  /* Encolhe antes do chip de status e do badge de PR, que têm tamanho fixo. */
  flex: 1 1 auto;
  display: flex;
  align-items: baseline;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
  padding: 2px 4px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font: inherit;
  font-size: var(--text-xs);
  text-align: left;
}

button.tl__name:hover {
  background: var(--color-surface-hover);
}

.tl__name--group {
  padding-left: 0;
}

.tl__key {
  flex-shrink: 0;
  color: var(--color-primary);
}

.tl__key[data-done] {
  color: var(--color-text-muted);
  text-decoration: line-through;
}

.tl__summary {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text);
}

.tl__count {
  flex-shrink: 0;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface);
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

/* Linha fina de progresso sob o nome do pai, como no print. */
.tl__progress {
  flex: 1;
  min-width: 24px;
  max-width: 70px;
  height: 3px;
  margin-left: auto;
  border-radius: 999px;
  background: var(--color-border-strong);
  overflow: hidden;
}

.tl__progress-fill {
  display: block;
  height: 100%;
  background: var(--color-primary);
}

.tl__status {
  flex-shrink: 0;
  max-width: 92px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  /* O fundo vem do stage_color do Jira (saturado nos dois temas): branco fixo. */
  color: #ffffff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tl__sp {
  flex-shrink: 0;
  padding: 0 3px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.tl__bar {
  position: absolute;
  top: 6px;
  height: 18px;
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
  overflow: hidden;
}

.tl__bar[data-projected] {
  box-shadow: inset -2px 0 0 var(--color-border-strong);
}

.tl__bar--group {
  top: 9px;
  height: 12px;
  background: var(--color-track-group);
}

.tl__bar-fill {
  display: block;
  height: 100%;
  border-radius: var(--radius-md);
  background: var(--color-primary);
}

.tl__segment {
  position: absolute;
  top: 0;
  bottom: 0;
}

.tl__projection {
  position: absolute;
  top: 0;
  bottom: 0;
  background: repeating-linear-gradient(
    135deg,
    var(--color-track-hatch) 0 4px,
    transparent 4px 8px
  );
}

.tl__not-started {
  position: absolute;
  top: 3px;
  right: 3px;
  color: var(--color-on-track-muted);
}

.tl__links {
  position: absolute;
  top: 0;
  pointer-events: none;
  z-index: 2;
}

.tl__link {
  fill: none;
  stroke: var(--color-text-muted);
  stroke-width: 1.5;
  stroke-dasharray: 3 3;
  pointer-events: stroke;
}

.tl__link-tip {
  fill: var(--color-text-muted);
}

.tl__legend {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: var(--space-2);
  font-size: 11px;
  color: var(--color-text-muted);
}
</style>
