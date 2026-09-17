<script setup>
import { computed, inject } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { CANVAS_MARKS, nodeMarks } from './canvasMarks'
import { Ban, CircleCheck, Layers, Link2, MessageSquareWarning, SquareCheck, StickyNote } from 'lucide-vue-next'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { PR_STATUS } from '@/constants/prStatus'
import { useUiStore } from '@/stores/ui'
import { safeUrl } from '@/utils/safeUrl'

const props = defineProps({
  data: { type: Object, required: true },
})

const issue = computed(() => props.data.issue)

const canvasMarks = inject(CANVAS_MARKS, null)
const marks = computed(() => nodeMarks(issue.value, canvasMarks?.value))

/**
 * A cor do card é a da etapa do status — a mesma do contorno do selo de status no
 * topo. PR e bloqueio têm sinal próprio (badge, marcador do canto, ícone e seta).
 * Status sem etapa mapeada (ou card parcial) fica na borda neutra.
 */
const tone = computed(() => issue.value.stage?.color ?? 'var(--color-border-strong)')

/**
 * Ícone de bloqueio só enquanto algum bloqueador não abriu PR: com a PR aberta já há
 * código de onde partir, e o card volta ao ícone do tipo e perde o "bloqueada por",
 * que lista só quem ainda falta abrir PR. A seta continua até o bloqueador concluir.
 */
const waitingBlocker = computed(() => (issue.value.blockers_without_pr ?? []).length > 0)
const jiraUrl = computed(() => safeUrl(issue.value.url))

const typeLabel = computed(() => issue.value.issue_type.toUpperCase())
const done = computed(() => issue.value.status_category === 'done')
const initials = computed(() =>
  (issue.value.assignee_name ?? '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase(),
)
const childCount = computed(() => issue.value.children.length)

/**
 * Marcador no canto superior direito: dá para varrer o canvas inteiro sem ler o
 * rodapé de cada card. Só os três estados que pedem decisão — o resto continua
 * contado pela cor da borda e pelo badge do rodapé.
 */
const CORNER = {
  aprovada: { icon: CircleCheck, title: PR_STATUS.aprovada.label },
  mergeada: { icon: CircleCheck, title: PR_STATUS.mergeada.label },
  ajustes_requisitados: { icon: MessageSquareWarning, title: PR_STATUS.ajustes_requisitados.label },
}

const corner = computed(() => {
  const status = issue.value.in_sprint ? issue.value.pr?.status : null
  const mark = status ? CORNER[status] : null
  return mark ? { ...mark, status, color: PR_STATUS[status].color } : null
})

/**
 * Sombra pulsante: o que está na mão do dev agora. Ajustes requisitados vem antes —
 * é review esperando resposta — e pinta a sombra com a cor do status de PR; tarefa em
 * desenvolvimento pulsa na cor da etapa. Pai e card fora da sprint não pulsam: são
 * contexto da árvore, não trabalho da sprint.
 */
const DEVELOPMENT_STAGE = 'desenvolvimento'

const pulse = computed(() => {
  const i = issue.value
  if (!i.in_sprint || i.is_parent_type) return null
  if (i.pr?.status === 'ajustes_requisitados') return { kind: 'ajustes', color: PR_STATUS.ajustes_requisitados.color }
  if (i.stage?.id === DEVELOPMENT_STAGE) return { kind: 'desenvolvimento', color: 'var(--tone)' }
  return null
})

/**
 * Ícone de lembretes no rodapé: abre o painel da tarefa direto nos lembretes. O clique
 * segue até o canvas, que seleciona o card e move a câmera como num clique comum — o
 * ícone só deixa pedida a vista de lembretes antes. Com Alt é destaque de status, não
 * abertura: o pedido ficaria esperando a próxima vez que o card fosse aberto.
 */
const noteCount = computed(() => issue.value.note_count ?? 0)
const notesLabel = computed(() =>
  noteCount.value ? `${noteCount.value} lembrete${noteCount.value > 1 ? 's' : ''} — abrir` : 'Lembretes: nenhum ainda — abrir',
)

function openNotes(event) {
  // Store pego no clique, não no setup: o card também é montado sem Pinia (testes do canvas).
  if (!event.altKey) useUiStore().requestIssueTab(issue.value.key, 'lembretes')
}

const CHANGE_LABELS = { status: 'status', pr: 'etapa do PR', story_points: 'Story Points', assignee: 'responsável' }

const updates = computed(() => {
  const fields = issue.value.unseen_changes ?? []
  return fields.length ? `Atualizada desde a última visita: ${fields.map((f) => CHANGE_LABELS[f] ?? f).join(', ')}` : null
})
</script>

<template>
  <article
    class="node"
    :class="{
      'node--parent': issue.is_parent_type,
      'node--outside': !issue.in_sprint && !issue.is_parent_type,
      'node--partial': issue.partial,
      'node--selected': data.selected,
      'node--done': done,
      'node--match': marks.match,
      'node--active': marks.active,
      'node--muted': marks.muted,
      'node--emphasized': marks.emphasized,
      'node--pulse': pulse,
    }"
    :style="{ '--tone': tone, '--pulse': pulse?.color }"
    :data-key="issue.key"
    :data-corner="corner?.status"
    :data-pulse="pulse?.kind"
    :title="`${issue.partial ? 'Fora do espelho local: dados do link' : issue.summary}\nAlt + clique: destacar os cards em ${issue.status}`"
  >
    <Handle id="top" type="target" :position="Position.Top" class="node__handle" />
    <Handle id="left" type="target" :position="Position.Left" class="node__handle" />

    <span v-if="corner" class="node__corner" :style="{ color: corner.color }" :title="corner.title">
      <component :is="corner.icon" :size="15" />
    </span>

    <span class="node__status" :title="`Status no Jira: ${issue.status}`">{{ issue.status }}</span>

    <header class="node__header">
      <span class="node__icon" :class="{ 'node__icon--blocked': waitingBlocker }">
        <Ban v-if="waitingBlocker" :size="14" />
        <Layers v-else-if="issue.is_parent_type" :size="14" />
        <CircleCheck v-else-if="done" :size="14" />
        <SquareCheck v-else :size="14" />
      </span>
      <span class="node__type">{{ typeLabel }}</span>
      <span class="node__divider" aria-hidden="true" />
      <!-- @click.stop: abrir o Jira não seleciona o card nem move a câmera. -->
      <a
        v-if="jiraUrl"
        class="node__key"
        :href="jiraUrl"
        target="_blank"
        rel="noopener noreferrer"
        :title="`Abrir ${issue.key} no Jira`"
        @click.stop
      >{{ issue.key }}</a>
      <span v-else class="node__key">{{ issue.key }}</span>
      <span v-if="issue.story_points != null" class="node__points" title="Story Points">{{ issue.story_points }} SP</span>
      <span v-if="issue.is_parent_type && childCount" class="node__points">{{ childCount }} filhas</span>
      <Link2 v-if="issue.parent_via === 'link'" :size="12" class="node__via" aria-label="pai por link" />
      <span v-if="!issue.is_mine && initials" class="node__avatar" :title="issue.assignee_name">{{ initials }}</span>
      <span v-if="updates" class="node__updated" role="status" :title="updates" :aria-label="updates" />
    </header>

    <h3 class="node__title">{{ issue.summary || issue.key }}</h3>

    <footer class="node__footer">
      <template v-if="issue.in_sprint && issue.pr">
        <PrStatusBadge :status="issue.pr.status" :pr-count="issue.pr.pr_count" :build-failed="issue.pr.build_failed" size="sm" />
        <span v-if="waitingBlocker" class="node__blocked">bloqueada por {{ issue.blockers_without_pr.join(', ') }}</span>
      </template>
      <button
        type="button"
        class="node__notes"
        :class="{ 'node__notes--filled': noteCount }"
        :title="notesLabel"
        :aria-label="notesLabel"
        @click="openNotes"
      >
        <StickyNote :size="13" />
        <span v-if="noteCount">{{ noteCount }}</span>
      </button>
    </footer>

    <Handle id="bottom" type="source" :position="Position.Bottom" class="node__handle" />
    <Handle id="right" type="source" :position="Position.Right" class="node__handle" />
  </article>
</template>

<style scoped>
.node {
  position: relative;
  box-sizing: border-box;
  width: 236px;
  height: 132px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1.5px solid color-mix(in srgb, var(--tone) 70%, transparent);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition:
    box-shadow var(--duration-fast),
    transform var(--duration-fast),
    opacity var(--duration-fast),
    filter var(--duration-fast);
}

.node:hover {
  box-shadow: var(--shadow-md);
}

.node--parent {
  background: color-mix(in srgb, var(--tone) 5%, var(--color-surface));
}

.node--outside {
  opacity: 0.7;
  border-style: dashed;
}

.node--partial {
  border-style: dashed;
}

.node--selected {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 30%, transparent), var(--shadow-md);
}

/* Marcador em cima do contorno: metade dentro, metade fora, com o fundo do card
   por baixo para a borda não atravessar o ícone. */
.node__corner {
  position: absolute;
  top: -9px;
  right: -9px;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--color-surface);
  box-shadow: 0 0 0 1.5px currentColor inset;
}

/* Busca no canvas: todo resultado fica visível, o da vez ganha o anel. */
.node--match {
  border-color: var(--color-primary);
}

.node--active {
  box-shadow: 0 0 0 3px var(--color-primary-focus-ring), var(--shadow-md);
}

/* Destaque de status (Alt + clique num card): os do mesmo status crescem, os outros
   desbotam. Sem destaque ligado, nenhum card muda. */
.node--emphasized {
  transform: scale(1.04);
  box-shadow: var(--shadow-md);
}

.node--muted {
  opacity: 0.4;
  filter: saturate(0.25);
}

.node__header {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 20px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.node__icon {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--tone) 14%, transparent);
  flex-shrink: 0;
  color: var(--tone);
}

/* Ícone de bloqueio fica vermelho mesmo com a cor do card vindo da etapa. */
.node__icon--blocked {
  background: var(--color-error-surface);
  color: var(--color-error);
}

/* Tipo é o que cede quando o cabeçalho aperta (ENHANCEMENTS, SUBTAREFA): chave e SP
   ficam inteiros. */
.node__type {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary);
}

.node__via {
  color: var(--color-text-muted);
}

.node__avatar {
  margin-left: auto;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--color-surface-muted);
  font-size: 9px;
  font-weight: 700;
  color: var(--color-text-secondary);
}

.node__title {
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: var(--text-sm);
  font-weight: 600;
  line-height: 17px;
  color: var(--color-text);
}

.node--done .node__title {
  color: var(--color-text-secondary);
}

.node__divider {
  flex-shrink: 0;
  width: 1px;
  height: 12px;
  background: var(--color-border-strong);
}

.node__key {
  flex-shrink: 0;
  font-weight: 600;
  white-space: nowrap;
  color: var(--color-text-secondary);
  text-decoration: none;
}

a.node__key:hover {
  color: var(--color-primary);
  text-decoration: underline;
}

.node__points {
  flex-shrink: 0;
  white-space: nowrap;
  padding: 0 5px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
}

/* Status do Jira sentado no contorno, no canto oposto ao marcador de PR. O fundo é
   opaco (mistura com a superfície) para a borda do card não atravessar o texto; a
   largura para antes do marcador do canto direito. */
.node__status {
  position: absolute;
  top: -9px;
  left: 10px;
  z-index: 1;
  box-sizing: border-box;
  max-width: calc(100% - 44px);
  height: 18px;
  padding: 0 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1.5px solid var(--tone);
  border-radius: 999px;
  background: color-mix(in srgb, var(--tone) 16%, var(--color-surface));
  font-size: 10px;
  font-weight: 600;
  line-height: 15px;
  letter-spacing: 0.2px;
  color: var(--color-text);
}

/* Bolinha de "teve atualização desde a última visita": some quando o card é aberto. */
.node__updated {
  position: relative;
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  margin-left: auto;
  border-radius: 50%;
  background: var(--color-success);
}

.node__avatar + .node__updated {
  margin-left: 0;
}

.node__updated::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--color-success);
  animation: node-updated 1.6s ease-out infinite;
}

@keyframes node-updated {
  from {
    transform: scale(1);
    opacity: 0.7;
  }

  to {
    transform: scale(2.6);
    opacity: 0;
  }
}

/* Sombra pulsante atrás do contorno. Fica num pseudo-elemento para não brigar com o
   box-shadow de seleção, busca e legenda — os dois anéis convivem. A cor-base é mais
   forte e o halo vai mais longe que o anel de seleção (3px a 30%), senão um card
   selecionado e um pulsando seriam indistinguíveis. */
.node--pulse::after {
  content: '';
  position: absolute;
  inset: -1.5px;
  z-index: -1;
  border-radius: inherit;
  pointer-events: none;
  animation: node-pulse 1.8s ease-in-out infinite;
}

@keyframes node-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 2px color-mix(in srgb, var(--pulse) 55%, transparent),
      0 0 8px 2px color-mix(in srgb, var(--pulse) 35%, transparent);
  }

  50% {
    box-shadow:
      0 0 0 6px color-mix(in srgb, var(--pulse) 30%, transparent),
      0 0 22px 8px color-mix(in srgb, var(--pulse) 45%, transparent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .node--pulse::after {
    animation: none;
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--pulse) 45%, transparent);
  }

  .node__updated::after {
    animation: none;
    opacity: 0;
  }
}

.node__footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 22px;
}

/* Sempre no canto direito do rodapé, com ou sem badge de PR ao lado. */
.node__notes {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 22px;
  margin-left: auto;
  padding: 0 5px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  cursor: pointer;
}

.node__notes--filled {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.node__notes:hover {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.node__blocked {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--color-error);
}

.node__handle {
  opacity: 0;
  pointer-events: none;
}
</style>
