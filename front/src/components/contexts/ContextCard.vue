<script setup>
import { computed, ref } from 'vue'
import { CircleCheck, CornerDownRight, ExternalLink, Pencil, RotateCcw, Trash2 } from 'lucide-vue-next'
import { CONTEXT_KINDS, RELATION_LABEL } from '@/constants/contextKinds'
import { highlightParts } from '@/utils/highlight'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  context: { type: Object, required: true },
  highlight: { type: String, default: '' },
  // Dentro de um grupo/painel da própria tarefa a chave de origem é redundante.
  hideIssue: { type: Boolean, default: false },
  // Texto do botão de resolver (ex.: "Resolver aqui" no painel de outra tarefa).
  resolveLabel: { type: String, default: 'Resolver' },
})
const emit = defineEmits(['edit', 'delete', 'resolve', 'reopen', 'open-issue'])

const BODY_CLAMP = 480

const kind = computed(() => CONTEXT_KINDS[props.context.kind] ?? CONTEXT_KINDS.summary)
const isOpenPoint = computed(() => props.context.kind === 'open_point')
const resolved = computed(() => props.context.status === 'resolved')
const expanded = ref(false)
const confirmingDelete = ref(false)
const longBody = computed(() => props.context.body.length > BODY_CLAMP)
const body = computed(() =>
  longBody.value && !expanded.value ? `${props.context.body.slice(0, BODY_CLAMP).trimEnd()}…` : props.context.body,
)
const relations = computed(() => props.context.relations.filter((r) => r.relation !== 'resolves'))
const parts = (text) => highlightParts(text, props.highlight)

function onDelete() {
  if (!confirmingDelete.value) {
    confirmingDelete.value = true
    return
  }
  confirmingDelete.value = false
  emit('delete', props.context)
}

function openIssue(issue) {
  emit('open-issue', issue)
}
</script>

<template>
  <article
    class="ctx"
    :class="{ 'ctx--resolved': resolved }"
    :style="{ '--kind-color': kind.color, '--kind-bg': kind.bg }"
    :data-id="context.id"
    :data-kind="context.kind"
  >
    <header class="ctx__header">
      <span class="ctx__kind"><component :is="kind.icon" :size="13" /> {{ kind.label }}</span>
      <span v-if="isOpenPoint && !resolved" class="ctx__status ctx__status--open">Em aberto</span>
      <span v-else-if="resolved" class="ctx__status ctx__status--resolved">
        <CircleCheck :size="12" /> Resolvido em
        <button type="button" class="ctx__link" @click="openIssue(context.resolved_in)">{{ context.resolved_in.key }}</button>
      </span>
      <button
        v-if="!hideIssue"
        type="button"
        class="ctx__issue"
        :class="{ 'ctx__issue--external': !context.issue.in_mirror }"
        :title="context.issue.summary || 'Fora do espelho local'"
        @click="openIssue(context.issue)"
      >
        {{ context.issue.key }}<ExternalLink v-if="!context.issue.in_mirror" :size="10" />
      </button>
      <span v-if="context.source === 'ai_approved'" class="ctx__ai" title="Rascunho da IA aprovado por você">IA</span>

      <div class="ctx__actions">
        <button v-if="isOpenPoint && !resolved" type="button" class="ctx__resolve" @click="emit('resolve', context)">
          <CircleCheck :size="13" /> {{ resolveLabel }}
        </button>
        <button v-if="resolved" type="button" title="Reabrir" aria-label="Reabrir" @click="emit('reopen', context)"><RotateCcw :size="13" /></button>
        <button type="button" title="Editar" aria-label="Editar" @click="emit('edit', context)"><Pencil :size="13" /></button>
        <button
          type="button"
          class="ctx__delete"
          :class="{ 'ctx__delete--confirm': confirmingDelete }"
          :title="confirmingDelete ? 'Clique de novo para excluir' : 'Excluir'"
          :aria-label="confirmingDelete ? 'Confirmar exclusão' : 'Excluir'"
          @click="onDelete"
          @blur="confirmingDelete = false"
        >
          <Trash2 :size="13" /><span v-if="confirmingDelete">Excluir?</span>
        </button>
      </div>
    </header>

    <h3 v-if="context.title" class="ctx__title">
      <mark v-for="(p, i) in parts(context.title)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
    </h3>
    <p v-if="context.body" class="ctx__body">
      <mark v-for="(p, i) in parts(body)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
    </p>
    <button v-if="longBody" type="button" class="ctx__more" @click="expanded = !expanded">{{ expanded ? 'Mostrar menos' : 'Mostrar tudo' }}</button>

    <p v-if="resolved && context.resolution" class="ctx__resolution">
      <CornerDownRight :size="13" />
      <span><mark v-for="(p, i) in parts(context.resolution)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark></span>
    </p>

    <footer class="ctx__footer">
      <span v-for="rel in relations" :key="rel.key" class="ctx__rel">
        {{ RELATION_LABEL[rel.relation] }}
        <button type="button" class="ctx__link" :class="{ 'ctx__link--external': !rel.in_mirror }" :title="rel.summary || 'Fora do espelho local'" @click="openIssue(rel)">{{ rel.key }}</button>
      </span>
      <span v-for="tag in context.tags" :key="tag" class="ctx__tag">#{{ tag }}</span>
      <time class="ctx__time" :datetime="context.updated_at" :title="new Date(context.updated_at).toLocaleString('pt-BR')">
        {{ formatRelative(context.updated_at) }}
      </time>
    </footer>
  </article>
</template>

<style scoped>
.ctx {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--kind-color);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}

.ctx--resolved {
  border-left-color: var(--color-success);
  background: var(--color-resolved-surface);
}

.ctx__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 26px;
}

.ctx__kind {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--kind-bg);
  color: var(--kind-color);
  font-size: 11px;
  font-weight: 600;
}

.ctx__status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
}

.ctx__status--open {
  color: var(--color-warning-text);
}

.ctx__status--resolved {
  color: var(--color-success);
}

.ctx__issue,
.ctx__link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
}

.ctx__issue {
  padding: 1px 6px;
  border: 1px solid var(--color-border-strong);
  border-radius: 999px;
}

.ctx__issue--external,
.ctx__link--external {
  color: var(--color-text-secondary);
}

.ctx__ai {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 10px;
  font-weight: 700;
}

.ctx__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

.ctx__actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 26px;
  min-width: 26px;
  padding: 0 6px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.ctx__actions button:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.ctx__actions .ctx__resolve {
  border: 1px solid var(--color-success-border);
  color: var(--color-success);
  font-weight: 600;
}

.ctx__actions .ctx__delete--confirm {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.ctx__title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  line-height: 20px;
  overflow-wrap: anywhere;
}

.ctx--resolved .ctx__title {
  color: var(--color-text-secondary);
}

.ctx__body {
  margin: 0;
  font-size: var(--text-sm);
  line-height: 20px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--color-text);
}

.ctx__more {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.ctx__resolution {
  display: flex;
  gap: 6px;
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--radius-md);
  background: var(--color-success-surface);
  font-size: var(--text-sm);
  white-space: pre-wrap;
  color: var(--color-text);
}

.ctx__resolution svg {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--color-success);
}

.ctx__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.ctx__rel {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.ctx__time {
  margin-left: auto;
}

mark {
  background: none;
  color: inherit;
}

mark.hit {
  border-radius: 3px;
  background: var(--color-mark);
}
</style>
