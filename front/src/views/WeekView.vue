<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BellRing,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Plus,
  RefreshCw,
  Scissors,
} from 'lucide-vue-next'

import IssueDrawer from '@/components/issue/IssueDrawer.vue'
import WeekIssueRow from '@/components/week/WeekIssueRow.vue'
import { NOTE_COLORS } from '@/constants/noteColors'
import { useContextsStore } from '@/stores/contexts'
import { useNotesStore } from '@/stores/notes'
import { useScreenContextStore } from '@/stores/screenContext'
import { useRefreshStore } from '@/stores/refresh'
import { isoDay, shiftDay, useWeekStore } from '@/stores/week'

const route = useRoute()
const router = useRouter()
const week = useWeekStore()
const notes = useNotesStore()
const contexts = useContextsStore()
const refresh = useRefreshStore()
const screen = useScreenContextStore()

const day = computed(() => (/^\d{4}-\d{2}-\d{2}$/.test(route.query.dia ?? '') ? route.query.dia : null))
const issueKey = computed(() => route.query.tarefa ?? null)
const data = computed(() => week.data)

screen.enter('week')
onBeforeUnmount(() => screen.enter(null))
watch(issueKey, (key) => screen.focusIssue(key), { immediate: true })

function setQuery(patch) {
  const query = { ...route.query, ...patch }
  for (const key of Object.keys(query)) if (query[key] === null || query[key] === '') delete query[key]
  router.replace({ query })
}

const reload = () => week.load(day.value)
watch(day, reload, { immediate: true })
// Lembrete/contexto salvo em qualquer tela: a semana reflete na hora.
watch(() => [notes.revision, contexts.revision], reload)
// Sync concluído ou "Recarregar".
watch(() => refresh.revision, reload)
watch(
  () => week.issueKeys,
  (keys) => screen.$patch({ sprintId: null, visibleIssueKeys: keys, filters: { semana: data.value?.start ?? null } }),
)

const rangeFormat = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short' })
const weekdayFormat = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: '2-digit', month: 'short' })
const timeFormat = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' })

const asDate = (d) => new Date(`${d}T12:00:00`)
const isCurrentWeek = computed(() => data.value && data.value.today >= data.value.start && data.value.today <= data.value.end)
const title = computed(() => {
  const d = data.value
  if (!d) return 'Semana'
  return `${rangeFormat.format(asDate(d.start))} – ${rangeFormat.format(asDate(d.end))}`
})
const weekLabel = computed(() => {
  const d = data.value
  if (!d) return ''
  if (isCurrentWeek.value) return 'Esta semana'
  const diff = Math.round((asDate(d.start) - asDate(shiftDay(d.today, -((asDate(d.today).getDay() + 6) % 7)))) / (7 * 86400000))
  if (diff === 1) return 'Próxima semana'
  if (diff === -1) return 'Semana passada'
  return diff > 0 ? `Daqui a ${diff} semanas` : `Há ${-diff} semanas`
})

function go(weeks) {
  const base = data.value?.start ?? isoDay(new Date())
  setQuery({ dia: shiftDay(base, weeks * 7) })
}

// Prazos e lembretes agrupados por dia da semana (só dias com algo).
function byDay(items, dayOf) {
  const map = new Map()
  for (const item of items) {
    const key = dayOf(item)
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(item)
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([d, list]) => ({ day: d, label: weekdayFormat.format(asDate(d)), items: list }))
}

const dueDays = computed(() => byDay(data.value?.due ?? [], (i) => i.due_date))
const reminderDays = computed(() => byDay(data.value?.reminders ?? [], (n) => isoDay(new Date(n.remind_at))))
const openSlicing = computed(() => (data.value?.slicing ?? []).filter((i) => i.status_category !== 'done'))
const doneSlicing = computed(() => (data.value?.slicing ?? []).filter((i) => i.status_category === 'done'))

function openIssue(key) {
  setQuery({ tarefa: key })
}

function newReminder() {
  // Sugere o dia de hoje (se for esta semana) ou a segunda da semana vista, às 9h.
  const base = isCurrentWeek.value ? null : data.value?.start
  const at = base ? new Date(`${base}T09:00:00`) : null
  notes.openEditor(null, { ...(at ? { remind_at: at.toISOString() } : {}), issue_keys: issueKey.value ? [issueKey.value] : [] })
}

function reminderState(note) {
  if (note.reminder_due) return 'due'
  if (note.reminded_at) return 'done'
  return 'upcoming'
}
</script>

<template>
  <div class="week-page">
    <section class="week">
      <header class="week__header card">
        <div class="week__nav">
          <CalendarDays :size="20" class="week__icon" />
          <div class="week__title">
            <h1>{{ title }}</h1>
            <span class="week__label" :data-current="isCurrentWeek || null">{{ weekLabel }}</span>
          </div>
          <div class="week__actions">
            <button type="button" class="btn btn--secondary" aria-label="Semana anterior" title="Semana anterior" @click="go(-1)"><ChevronLeft :size="16" /></button>
            <button type="button" class="btn btn--secondary" :disabled="isCurrentWeek" @click="setQuery({ dia: null })">Hoje</button>
            <button type="button" class="btn btn--secondary" aria-label="Próxima semana" title="Próxima semana" @click="go(1)"><ChevronRight :size="16" /></button>
            <button type="button" class="btn btn--secondary" title="Recarregar tudo: a semana, o painel aberto e as outras telas" :disabled="week.loading" @click="refresh.reload()">
              <RefreshCw :size="14" :class="{ spin: week.loading }" />
            </button>
          </div>
        </div>
        <p v-if="data && !data.filtered_by_assignee" class="week__warn">
          A conexão com o Jira não guardou seu accountId: as listas mostram todas as tarefas do espelho, não só as suas. Teste a conexão de novo em Configurações.
        </p>
      </header>

      <p v-if="week.error" class="week__error card" role="alert">{{ week.error }}</p>

      <div v-else-if="data" class="week__grid">
        <!-- Com prazo: o que tem data nesta semana -->
        <div class="week__col">
          <!-- 2. Prazo na semana -->
          <section class="block card" data-block="due">
            <h2 class="block__title"><CalendarClock :size="16" /> Prazo nesta semana <small>{{ data.due.length }}</small></h2>
            <template v-if="data.overdue.length">
              <h3 class="block__sub block__sub--late">Atrasadas <small>{{ data.overdue.length }}</small></h3>
              <ul class="block__list">
                <WeekIssueRow v-for="issue in data.overdue" :key="issue.key" :issue="issue" :today="data.today" :selected="issue.key === issueKey" show-due @open="openIssue" />
              </ul>
            </template>
            <template v-for="group in dueDays" :key="group.day">
              <h3 class="block__sub" :data-today="group.day === data.today || null">{{ group.label }}</h3>
              <ul class="block__list">
                <WeekIssueRow v-for="issue in group.items" :key="issue.key" :issue="issue" :today="data.today" :selected="issue.key === issueKey" @open="openIssue" />
              </ul>
            </template>
            <p v-if="!data.due.length && !data.overdue.length" class="block__empty">
              Nenhuma tarefa sua com data de entrega nesta semana. (O prazo vem do campo “Data limite” do Jira.)
            </p>
          </section>

          <!-- 3. Lembretes da semana -->
          <section class="block card" data-block="reminders">
            <h2 class="block__title">
              <BellRing :size="16" /> Lembretes da semana <small>{{ data.reminders.length }}</small>
              <button type="button" class="block__action" @click="newReminder"><Plus :size="13" /> Novo</button>
            </h2>
            <template v-if="data.pending_reminders.length">
              <h3 class="block__sub block__sub--late">Pendentes de antes <small>{{ data.pending_reminders.length }}</small></h3>
              <ul class="block__list">
                <li v-for="note in data.pending_reminders" :key="note.id" class="reminder" :data-id="note.id" data-state="due" :style="{ '--note-border': (NOTE_COLORS[note.color] ?? NOTE_COLORS.yellow).border }">
                  <button type="button" class="reminder__main" @click="notes.openEditor(note)">
                    <span class="reminder__when">{{ rangeFormat.format(new Date(note.remind_at)) }} {{ timeFormat.format(new Date(note.remind_at)) }}</span>
                    <span class="reminder__title">{{ note.title || note.body.slice(0, 80) }}</span>
                  </button>
                  <button type="button" class="reminder__ack" title="Marcar como visto" @click="notes.acknowledge(note.id)">Concluir</button>
                </li>
              </ul>
            </template>
            <template v-for="group in reminderDays" :key="group.day">
              <h3 class="block__sub" :data-today="group.day === data.today || null">{{ group.label }}</h3>
              <ul class="block__list">
                <li
                  v-for="note in group.items"
                  :key="note.id"
                  class="reminder"
                  :data-id="note.id"
                  :data-state="reminderState(note)"
                  :style="{ '--note-border': (NOTE_COLORS[note.color] ?? NOTE_COLORS.yellow).border }"
                >
                  <button type="button" class="reminder__main" @click="notes.openEditor(note)">
                    <span class="reminder__when">{{ timeFormat.format(new Date(note.remind_at)) }}</span>
                    <span class="reminder__title">{{ note.title || note.body.slice(0, 80) }}</span>
                    <span v-for="i in note.issues" :key="i.key" class="reminder__issue">{{ i.key }}</span>
                  </button>
                  <button v-if="note.reminder_due" type="button" class="reminder__ack" title="Marcar como visto" @click="notes.acknowledge(note.id)">Concluir</button>
                  <span v-else-if="note.reminded_at" class="reminder__seen">visto</span>
                </li>
              </ul>
            </template>
            <p v-if="!data.reminders.length && !data.pending_reminders.length" class="block__empty">Nenhum lembrete agendado para esta semana.</p>
          </section>
        </div>
        <!-- Sem data: o que precisa de atenção, mas não tem dia marcado -->
        <div class="week__col">
          <!-- 4. Analisar e fatiar -->
          <section class="block card" data-block="slicing">
            <h2 class="block__title"><Scissors :size="16" /> Analisar e fatiar <small>{{ openSlicing.length }}</small></h2>
            <p class="block__hint">Cards que viram um Enhancements em backlog — análise, não código.</p>
            <ul v-if="openSlicing.length" class="block__list">
              <WeekIssueRow v-for="issue in openSlicing" :key="issue.key" :issue="issue" :today="data.today" :selected="issue.key === issueKey" @open="openIssue" />
            </ul>
            <template v-if="doneSlicing.length">
              <h3 class="block__sub">Concluídos nesta semana <small>{{ doneSlicing.length }}</small></h3>
              <ul class="block__list">
                <WeekIssueRow v-for="issue in doneSlicing" :key="issue.key" :issue="issue" :today="data.today" :selected="issue.key === issueKey" @open="openIssue" />
              </ul>
            </template>
            <p v-if="!data.slicing.length" class="block__empty">Nenhum card “Analisar e fatiar” seu nesta semana.</p>
          </section>
          <!-- 1. Minhas sem sprint -->
          <section class="block card" data-block="without-sprint">
            <h2 class="block__title"><Inbox :size="16" /> Minhas sem sprint <small>{{ data.without_sprint.length }}</small></h2>
            <p class="block__hint">Em aberto, fora de sprint ativa ou futura — inclui o que sobrou de sprint fechada.</p>
            <ul v-if="data.without_sprint.length" class="block__list">
              <WeekIssueRow v-for="issue in data.without_sprint" :key="issue.key" :issue="issue" :today="data.today" :selected="issue.key === issueKey" show-due @open="openIssue" />
            </ul>
            <p v-else class="block__empty">Nada solto: tudo que é seu está numa sprint.</p>
          </section>
        </div>
      </div>

      <p v-else class="week__loading">Carregando a semana…</p>
    </section>

    <IssueDrawer v-if="issueKey" :issue-key="issueKey" @close="setQuery({ tarefa: null })" @open="(k) => setQuery({ tarefa: k })" />
  </div>
</template>

<style scoped>
.week-page {
  height: 100%;
  display: flex;
  gap: var(--space-4);
}

.week {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.week__header {
  padding: var(--space-4) var(--space-5);
}

.week__nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.week__icon {
  color: var(--color-primary);
}

.week__title {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.week__title h1 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
}

.week__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
}

.week__label[data-current] {
  color: var(--color-primary);
}

.week__actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.week__actions .btn {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
}

.week__warn {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
  font-size: var(--text-sm);
}

.week__error {
  padding: var(--space-4);
  color: var(--color-error);
}

.week__loading {
  color: var(--color-text-muted);
}

.week__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: var(--space-4);
  align-items: start;
}

.week__col {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

.block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-4);
}

.block__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.block__title svg {
  color: var(--color-primary);
}

.block__title small {
  padding: 0 7px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.block__action {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  padding: 3px 8px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.block__action:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.block__hint,
.block__empty {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.block__empty {
  padding: var(--space-3) 0;
  font-size: var(--text-sm);
}

.block__sub {
  margin: var(--space-2) 0 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.block__sub[data-today] {
  color: var(--color-primary);
}

.block__sub--late {
  color: var(--color-error);
}

.block__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.reminder {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 2px 0;
}

.reminder + .reminder {
  border-top: 1px solid var(--color-border);
}

.reminder__main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 7px 8px;
  border: 0;
  border-left: 3px solid var(--note-border);
  border-radius: var(--radius-sm);
  background: none;
  font: inherit;
  font-size: var(--text-sm);
  text-align: left;
}

.reminder__main:hover {
  background: var(--color-surface-muted);
}

.reminder__when {
  flex-shrink: 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.reminder[data-state='due'] .reminder__when {
  color: var(--color-error);
}

.reminder__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reminder[data-state='done'] .reminder__title {
  color: var(--color-text-muted);
}

.reminder__issue {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
}

.reminder__ack {
  flex-shrink: 0;
  padding: 3px 8px;
  border: 1px solid var(--color-success-border);
  border-radius: var(--radius-md);
  background: none;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-success);
}

.reminder__seen {
  font-size: 11px;
  color: var(--color-text-muted);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
