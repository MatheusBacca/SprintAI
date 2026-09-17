<script setup>
import { computed, ref } from 'vue'
import { Archive, ArchiveRestore, BellRing, CircleCheck, Pencil, Pin, PinOff, Trash2 } from 'lucide-vue-next'
import { NOTE_COLORS } from '@/constants/noteColors'
import { formatDateTime } from '@/utils/datetime'
import { highlightParts } from '@/utils/highlight'

const props = defineProps({
  note: { type: Object, required: true },
  highlight: { type: String, default: '' },
})
const emit = defineEmits(['edit', 'toggle-pin', 'toggle-archive', 'delete', 'open-issue', 'select-tag', 'complete'])

const confirmingDelete = ref(false)
const palette = computed(() => NOTE_COLORS[props.note.color] ?? NOTE_COLORS.yellow)

const reminder = computed(() => {
  const n = props.note
  if (!n.remind_at) return null
  if (n.reminder_due) return { tone: 'due', text: `Venceu · ${formatDateTime(n.remind_at)}` }
  if (n.reminded_at) return { tone: 'done', text: `Concluído · ${formatDateTime(n.remind_at)}` }
  return { tone: 'upcoming', text: formatDateTime(n.remind_at) }
})

// Destaque do termo buscado, sem v-html: quebra o texto em partes.
const parts = (text) => highlightParts(text, props.highlight)

function onDelete() {
  if (!confirmingDelete.value) {
    confirmingDelete.value = true
    return
  }
  confirmingDelete.value = false
  emit('delete', props.note)
}
</script>

<template>
  <article
    class="note"
    :class="{ 'note--pinned': note.pinned, 'note--archived': note.archived }"
    :style="{ '--note-bg': palette.bg, '--note-border': palette.border, '--note-accent': palette.accent }"
    :data-id="note.id"
    tabindex="0"
    @dblclick="emit('edit', note)"
    @keydown.enter.self="emit('edit', note)"
  >
    <header class="note__header">
      <h3 v-if="note.title" class="note__title">
        <mark v-for="(p, i) in parts(note.title)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
      </h3>
      <div class="note__actions">
        <button type="button" :title="note.pinned ? 'Desafixar' : 'Fixar'" @click="emit('toggle-pin', note)">
          <PinOff v-if="note.pinned" :size="14" />
          <Pin v-else :size="14" />
        </button>
        <button type="button" title="Editar" @click="emit('edit', note)"><Pencil :size="14" /></button>
        <button type="button" :title="note.archived ? 'Restaurar' : 'Arquivar'" @click="emit('toggle-archive', note)">
          <ArchiveRestore v-if="note.archived" :size="14" />
          <Archive v-else :size="14" />
        </button>
        <button
          type="button"
          class="note__delete"
          :class="{ 'note__delete--confirm': confirmingDelete }"
          :title="confirmingDelete ? 'Clique de novo para excluir' : 'Excluir'"
          @click="onDelete"
          @blur="confirmingDelete = false"
        >
          <Trash2 :size="14" />
          <span v-if="confirmingDelete">Excluir?</span>
        </button>
      </div>
    </header>

    <p v-if="note.body" class="note__body">
      <mark v-for="(p, i) in parts(note.body)" :key="i" :class="{ hit: p.hit }">{{ p.text }}</mark>
    </p>

    <p v-if="reminder" class="note__reminder" :data-tone="reminder.tone">
      <CircleCheck v-if="reminder.tone === 'done'" :size="13" />
      <BellRing v-else :size="13" />
      {{ reminder.text }}
      <!-- Mesma ação do "Concluir" da notificação; vale também antes de vencer. -->
      <button
        v-if="reminder.tone !== 'done' && !note.archived"
        type="button"
        class="note__complete"
        title="Concluir lembrete"
        @click="emit('complete', note)"
      >
        <CircleCheck :size="13" /> Concluir
      </button>
    </p>

    <footer v-if="note.tags.length || note.issues.length || note.repos?.length" class="note__footer">
      <button
        v-for="issue in note.issues"
        :key="issue.key"
        type="button"
        class="note__issue"
        :class="{ 'note__issue--external': !issue.in_mirror }"
        :title="issue.summary || 'Fora do espelho local'"
        @click="emit('open-issue', issue)"
      >
        {{ issue.key }}
      </button>
      <span v-for="repo in note.repos ?? []" :key="`repo:${repo}`" class="note__repo" title="Repositório citado">@{{ repo }}</span>
      <button v-for="tag in note.tags" :key="tag" type="button" class="note__tag" @click="emit('select-tag', tag)">
        #{{ tag }}
      </button>
    </footer>
  </article>
</template>

<style scoped>
.note {
  break-inside: avoid;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4) var(--space-4);
  border: 1px solid var(--note-border);
  border-top-width: 4px;
  border-radius: var(--radius-lg);
  background: var(--note-bg);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--duration-fast), transform var(--duration-fast);
}

.note:hover,
.note:focus-visible {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.note--archived {
  opacity: 0.7;
}

.note__header {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  min-height: 20px;
}

.note__title {
  flex: 1;
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  line-height: 20px;
  overflow-wrap: anywhere;
}

/* Flutuam sobre o canto do card: escondidas não roubam largura do título. */
.note__actions {
  position: absolute;
  top: -6px;
  right: -8px;
  display: flex;
  gap: 2px;
  padding: 2px;
  border-radius: var(--radius-md);
  background: var(--note-bg);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-fast);
}

.note:hover .note__actions,
.note:focus-within .note__actions {
  opacity: 1;
  pointer-events: auto;
  box-shadow: var(--shadow-sm);
}

.note__actions button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  min-width: 26px;
  justify-content: center;
  padding: 0 4px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--note-accent);
  font-size: var(--text-xs);
}

.note__actions button:hover {
  background: var(--note-scrim);
}

.note__delete--confirm {
  background: var(--color-error-surface) !important;
  color: var(--color-error) !important;
}

.note__body {
  margin: 0;
  font-size: var(--text-sm);
  line-height: 20px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--color-text);
  display: -webkit-box;
  -webkit-line-clamp: 12;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

mark {
  background: none;
  color: inherit;
}

mark.hit {
  border-radius: 3px;
  background: var(--color-mark);
}

.note__reminder {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--note-accent);
}

.note__complete {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  padding: 2px 8px;
  border: 1px solid var(--note-scrim-border);
  border-radius: 999px;
  background: var(--note-inset);
  font: inherit;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text);
}

.note__complete:hover {
  border-color: var(--color-success-border);
  background: var(--color-success-surface);
  color: var(--color-success);
}

.note__reminder[data-tone='due'] {
  color: var(--color-error);
}

.note__reminder[data-tone='done'] {
  color: var(--color-text-muted);
  font-weight: 500;
}

.note__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.note__issue,
.note__repo,
.note__tag {
  padding: 1px 8px;
  border: 0;
  border-radius: 999px;
  background: var(--note-inset);
  font-size: 11px;
  font-weight: 600;
  color: var(--note-accent);
}

.note__issue {
  border: 1px solid var(--note-border);
}

.note__issue--external {
  opacity: 0.75;
}

.note__issue:hover,
/* Vínculos com as cores do editor: tarefa em roxo, repositório em azul. */
.note__issue {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.note__repo {
  background: var(--color-repo-soft);
  color: var(--color-repo);
}

.note__tag:hover {
  background: var(--note-inset-strong);
}
</style>
