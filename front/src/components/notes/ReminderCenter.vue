<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BellRing, X } from 'lucide-vue-next'
import { api } from '@/services/api'
import { useNotesStore } from '@/stores/notes'
import { formatDateTime } from '@/utils/datetime'

const props = defineProps({
  pollMs: { type: Number, default: 30_000 },
})

const store = useNotesStore()
const toasts = ref([])
const notified = new Set() // notificação do Windows: uma vez por lembrete na sessão
let timer = null

function notifyBrowser(note) {
  if (notified.has(note.id)) return
  notified.add(note.id)
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
  try {
    const n = new Notification(note.title || 'Lembrete do SprintAI', {
      body: (note.body || '').slice(0, 180),
      tag: `sprintai-note-${note.id}`,
    })
    n.onclick = () => {
      window.focus()
      store.openEditor(note)
      n.close()
    }
  } catch {
    // Notificações podem estar bloqueadas pelo sistema: o aviso no app continua.
  }
}

async function poll() {
  try {
    const due = await api.get('/notes/reminders/due')
    const known = new Set(toasts.value.map((t) => t.id))
    for (const note of due) {
      if (!known.has(note.id)) toasts.value.push(note)
      notifyBrowser(note)
    }
    // Lembrete resolvido em outra tela some daqui também.
    const dueIds = new Set(due.map((n) => n.id))
    toasts.value = toasts.value.filter((t) => dueIds.has(t.id))
  } catch {
    // API/banco fora do ar: tenta no próximo ciclo.
  }
}

async function acknowledge(note) {
  toasts.value = toasts.value.filter((t) => t.id !== note.id)
  await store.acknowledge(note.id).catch(() => {})
}

async function snooze(note, minutes) {
  toasts.value = toasts.value.filter((t) => t.id !== note.id)
  notified.delete(note.id)
  await store.snooze(note.id, minutes).catch(() => {})
}

function open(note) {
  store.openEditor(note)
}

onMounted(() => {
  poll()
  timer = setInterval(poll, props.pollMs)
})
onBeforeUnmount(() => clearInterval(timer))
// Salvou/adiou/concluiu um lembrete em qualquer tela: reavalia na hora, sem esperar o ciclo.
watch(() => store.revision, poll)

defineExpose({ poll })
</script>

<template>
  <Teleport to="body">
    <section v-if="toasts.length" class="reminders" aria-live="polite" aria-label="Lembretes">
      <article v-for="note in toasts" :key="note.id" class="reminder" :data-id="note.id">
        <BellRing :size="18" class="reminder__icon" />
        <div class="reminder__content">
          <p class="reminder__title">{{ note.title || note.body.slice(0, 60) }}</p>
          <p class="reminder__when">{{ formatDateTime(note.remind_at) }}<template v-if="note.issues.length"> · {{ note.issues.map((i) => i.key).join(', ') }}</template></p>
          <div class="reminder__actions">
            <button type="button" class="btn btn--secondary" @click="open(note)">Abrir</button>
            <button type="button" class="btn btn--secondary" @click="snooze(note, 10)">Adiar 10 min</button>
            <button type="button" class="btn btn--secondary" @click="snooze(note, 60)">1 h</button>
            <button type="button" class="btn btn--primary" @click="acknowledge(note)">Concluir</button>
          </div>
        </div>
        <button type="button" class="reminder__close" title="Marcar como visto" @click="acknowledge(note)"><X :size="14" /></button>
      </article>
    </section>
  </Teleport>
</template>

<style scoped>
.reminders {
  position: fixed;
  right: var(--space-5);
  bottom: var(--space-5);
  z-index: calc(var(--z-modal) - 1);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: min(380px, calc(100vw - 32px));
}

.reminder {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--note-yellow-border);
  border-left-width: 4px;
  border-radius: var(--radius-lg);
  background: var(--note-yellow-bg);
  box-shadow: var(--shadow-modal);
}

.reminder__icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--note-yellow-accent);
}

.reminder__content {
  flex: 1;
  min-width: 0;
}

.reminder__title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.reminder__when {
  margin: 2px 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.reminder__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.reminder__actions .btn {
  padding: 4px 10px;
  font-size: var(--text-xs);
}

.reminder__close {
  align-self: flex-start;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}
</style>
