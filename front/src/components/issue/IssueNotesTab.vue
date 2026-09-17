<script setup>
import { onMounted, ref, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import NoteCard from '@/components/notes/NoteCard.vue'
import { useNotesStore } from '@/stores/notes'

const props = defineProps({
  issueKey: { type: String, required: true },
})
const emit = defineEmits(['open', 'count'])

const notes = useNotesStore()
const items = ref([])
const loading = ref(false)
const error = ref(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const result = await notes.fetch({ issue_key: props.issueKey, include_archived: true, limit: 100 })
    items.value = result.items
    emit('count', result.items.filter((n) => !n.archived).length)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.issueKey, notes.revision], load)

function openIssue(issue) {
  if (issue.key !== props.issueKey && issue.in_mirror) emit('open', issue.key)
}
</script>

<template>
  <div class="issue-notes">
    <button type="button" class="btn btn--secondary issue-notes__new" @click="notes.openEditor(null, { issue_keys: [issueKey] })">
      <Plus :size="14" /> Novo lembrete para {{ issueKey }}
    </button>

    <p v-if="error" class="issue-notes__empty" role="alert">{{ error }}</p>
    <p v-else-if="!loading && !items.length" class="issue-notes__empty">
      Nenhum lembrete vinculado. Anote aqui o que vale lembrar quando voltar a esta tarefa (ou numa próxima).
    </p>

    <NoteCard
      v-for="note in items"
      :key="note.id"
      :note="note"
      @edit="notes.openEditor"
      @toggle-pin="(n) => notes.patch(n.id, { pinned: !n.pinned })"
      @toggle-archive="(n) => notes.patch(n.id, { archived: !n.archived })"
      @delete="(n) => notes.remove(n.id)"
      @complete="(n) => notes.acknowledge(n.id)"
      @open-issue="openIssue"
    />
  </div>
</template>

<style scoped>
.issue-notes {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.issue-notes__new {
  align-self: flex-start;
}

.issue-notes__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.issue-notes :deep(.note) {
  margin-bottom: 0;
}
</style>
