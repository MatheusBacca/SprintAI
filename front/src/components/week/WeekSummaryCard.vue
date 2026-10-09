<script setup>
import { computed } from 'vue'
import { CircleCheck, Undo2 } from 'lucide-vue-next'

/**
 * Card do kanban do Resumo da semana: a tarefa na coluna da etapa em que terminou o dia.
 * O caminho inteiro do dia (cada status, a hora e quem mexeu) fica no title — o card mostra
 * onde ela parou e de onde veio.
 */
const props = defineProps({
  issue: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
const emit = defineEmits(['open'])

const timeFormat = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' })
const NO_STAGE = 'var(--color-border-strong)'

const end = computed(() => props.issue.moves.at(-1))
const delivered = computed(() => props.issue.outcome === 'entregue')
const back = computed(() => props.issue.outcome === 'voltou')

// Fui eu: não precisa dizer. Outro (ou não se sabe mais, depois da retenção do feed): diz quem.
const lastBy = computed(() => (end.value.by_me !== true && end.value.author_name ? end.value.author_name.split(' ')[0] : null))

// De onde veio. Na mesma etapa (DISPONIVEL PARA REVIEW → Em Review) a etapa não diz nada,
// então vai o status.
const origin = computed(() => {
  const { from_stage: stage, from_status: status } = props.issue
  if (!status) return null
  return stage && stage.id !== end.value.stage?.id ? stage.label : status
})

const trail = computed(() => {
  const who = (m) => (m.by_me ? 'você' : (m.author_name ?? 'alguém'))
  const lines = props.issue.moves.map((m) => `${timeFormat.format(new Date(m.at))}  ${m.status} (${who(m)})`)
  if (props.issue.from_status) lines.unshift(`Começou o dia em ${props.issue.from_status}`)
  if (delivered.value) lines.push('Entregue')
  return `${props.issue.key} · ${props.issue.summary}\n${lines.join('\n')}`
})
</script>

<template>
  <li
    class="scard"
    :class="{ 'scard--selected': selected }"
    :data-key="issue.key"
    :data-outcome="issue.outcome"
    :style="{ '--tone': end.stage?.color ?? NO_STAGE }"
  >
    <button type="button" class="scard__main" :title="trail" :aria-current="selected ? 'true' : undefined" @click="emit('open', issue.key)">
      <span class="scard__head">
        <strong class="scard__key">{{ issue.key }}</strong>
        <CircleCheck v-if="delivered" :size="13" class="scard__done" />
        <span v-if="issue.story_points != null" class="scard__sp">{{ issue.story_points }} SP</span>
      </span>
      <span class="scard__summary">{{ issue.summary }}</span>
      <span class="scard__status">
        {{ end.status }}<span v-if="lastBy" class="scard__who"> · {{ lastBy }}</span>
      </span>
      <span v-if="origin" class="scard__from" :class="{ 'scard__from--back': back }">
        <Undo2 v-if="back" :size="11" /> {{ back ? 'voltou de' : 'de' }} {{ origin }}
      </span>
    </button>
  </li>
</template>

<style scoped>
.scard {
  list-style: none;
}

.scard__main {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  font: inherit;
  text-align: left;
}

/* Só a entrega ganha a cor da etapa: é o que o resumo existe para mostrar. */
.scard[data-outcome='entregue'] .scard__main {
  border-left-color: var(--tone);
}

.scard__main:hover,
.scard--selected .scard__main {
  background: var(--color-primary-soft);
}

.scard--selected .scard__main {
  border-color: var(--color-primary);
  border-left-color: var(--tone);
}

.scard__head {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
}

.scard__key {
  color: var(--color-primary);
  white-space: nowrap;
}

.scard__done {
  flex-shrink: 0;
  color: var(--tone);
}

.scard__sp {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.scard__summary {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-size: var(--text-xs);
  line-height: 1.35;
  color: var(--color-text);
}

.scard__status,
.scard__from {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scard__status {
  font-weight: 600;
  color: var(--color-text-secondary);
}

.scard__who,
.scard__from {
  font-weight: 500;
  color: var(--color-text-muted);
}

.scard__from {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.scard__from--back {
  font-weight: 600;
  color: var(--color-warning-text);
}
</style>
