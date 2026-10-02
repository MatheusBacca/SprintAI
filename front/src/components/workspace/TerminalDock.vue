<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, ChevronUp, Plus, RotateCcw, SquareTerminal, X } from 'lucide-vue-next'
import { isInside, useTerminalsStore } from '@/stores/terminals'

// O xterm é o pedaço pesado do Workspace: só carrega quando um terminal aparece.
const TerminalPane = defineAsyncComponent(() => import('./TerminalPane.vue'))

/**
 * Terminais do Workspace, embaixo da área principal: um PowerShell por repo, aberto na
 * pasta dele. Mostra as sessões cujo `cwd` cai num dos repos do workspace — o terminal do
 * monitoria aberto noutro workspace aparece aqui também, é o mesmo shell.
 *
 * Até três ficam lado a lado; passando disso, viram abas.
 *
 * **Abre sozinho** um terminal para cada repo do workspace que ainda não tem um — é o que o
 * dev quer ao abrir as tarefas. Fechar um terminal à mão vale para aquele workspace: ele não
 * volta sozinho (fica salvo neste navegador), e o "+" do cabeçalho reabre.
 */
const props = defineProps({
  /** Repos com clone local: `{ slug, path }`. */
  repos: { type: Array, required: true },
  /** Todos os repos de `C:\projects`, para abrir terminal num que não está no workspace. */
  allRepos: { type: Array, default: () => [] },
  selectedRepo: { type: String, default: null },
  collapsed: { type: Boolean, default: false },
  /** Workspace aberto: a lista de terminais fechados à mão é por workspace. */
  workspaceId: { type: Number, default: null },
  /** Repos da tarefa aberta no painel: o terminal deles vem para a frente. */
  focusRepos: { type: Array, default: () => [] },
})
const emit = defineEmits(['toggle', 'pin-repo', 'open-folder'])

const SIDE_BY_SIDE = 3

const store = useTerminalsStore()
const folders = computed(() => props.repos.map((r) => r.path))
const sessions = computed(() => store.sessionsIn(folders.value))
const activeId = ref(null)
const tabbed = computed(() => sessions.value.length > SIDE_BY_SIDE)
const extraRepos = computed(() => {
  const listed = new Set(props.repos.map((r) => r.slug))
  return props.allRepos.filter((r) => !listed.has(r.slug))
})
const adding = ref('')

function repoOf(session) {
  return props.repos.find((r) => isInside(session.cwd, r.path)) ?? null
}

// --- Abrir sozinho -------------------------------------------------------------------------

const DISMISSED_KEY = 'sprintai.workspace.terminals.dismissed'
// O terminal host aceita 12; seis abertos sozinhos deixam folga para os abertos à mão.
const AUTO_LIMIT = 6

function readDismissed() {
  try {
    return JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? '{}') ?? {}
  } catch {
    return {}
  }
}

const dismissed = ref(readDismissed())

function isDismissed(slug) {
  return (dismissed.value[props.workspaceId] ?? []).includes(slug)
}

function setDismissed(slug, on) {
  if (!props.workspaceId || !slug) return
  const current = new Set(dismissed.value[props.workspaceId] ?? [])
  if (on) current.add(slug)
  else current.delete(slug)
  dismissed.value = { ...dismissed.value, [props.workspaceId]: [...current] }
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(dismissed.value))
  } catch {
    // Sem localStorage: o terminal fechado volta na próxima vez.
  }
}

const autoOpening = new Set()

/**
 * Um terminal por repo do workspace. Espera a lista de sessões do terminal host (`synced`):
 * antes dela não dá para saber o que já existe, e abriria em dobro. Sessão encerrada também
 * conta como existente — ela fica na tela com o "reabrir".
 */
async function autoOpen() {
  if (!props.workspaceId || !store.synced || store.available === false) return
  let budget = AUTO_LIMIT - sessions.value.filter((s) => s.alive).length
  for (const repo of props.repos) {
    if (budget <= 0) return
    if (isDismissed(repo.slug) || autoOpening.has(repo.path)) continue
    if (store.sessionsIn([repo.path]).length) continue
    autoOpening.add(repo.path)
    budget -= 1
    try {
      await store.open({ cwd: repo.path, label: repo.slug })
    } finally {
      autoOpening.delete(repo.path)
    }
  }
}

watch(
  [() => store.synced, () => folders.value.join('|'), () => props.workspaceId],
  () => autoOpen(),
  { immediate: true },
)

// Tarefa aberta no painel: o terminal do repo dela vem para a frente.
watch(
  () => props.focusRepos.join('|'),
  () => {
    const session = sessions.value.find((s) => props.focusRepos.includes(repoOf(s)?.slug))
    if (session) activeId.value = session.id
  },
)

function closeSession(session) {
  setDismissed(repoOf(session)?.slug, true)
  store.close(session.id)
}

// O stream só é pedido com o terminal host no ar. Fora do ar, pergunta de novo de tempos
// em tempos: rodar o atalho do SprintAI com a tela aberta traz os terminais sem recarregar.
const HEALTH_RETRY_MS = 10_000
let acquired = false
let healthTimer = null

async function ensureStream() {
  if (await store.checkHealth()) {
    if (!acquired) {
      store.acquire()
      acquired = true
    }
    return
  }
  healthTimer = setTimeout(ensureStream, HEALTH_RETRY_MS)
}

onMounted(ensureStream)
onBeforeUnmount(() => {
  clearTimeout(healthTimer)
  if (acquired) store.release()
})

// Escolher um repo na coluna da esquerda traz o terminal dele para a frente.
watch(
  () => props.selectedRepo,
  (slug) => {
    const session = sessions.value.find((s) => repoOf(s)?.slug === slug)
    if (session) activeId.value = session.id
  },
)

watch(sessions, (list) => {
  if (!list.some((s) => s.id === activeId.value)) activeId.value = list.at(-1)?.id ?? null
})

async function openIn(repo) {
  setDismissed(repo.slug, false)
  const session = await store.open({ cwd: repo.path, label: repo.slug })
  if (session) activeId.value = session.id
}

async function openOther() {
  const repo = props.allRepos.find((r) => r.slug === adding.value)
  adding.value = ''
  if (!repo) return
  // O repo entra no workspace: senão o terminal abria e sumia da lista na hora.
  emit('pin-repo', repo.slug)
  await openIn(repo)
}

const selected = computed(() => props.repos.find((r) => r.slug === props.selectedRepo) ?? props.repos[0] ?? null)
</script>

<template>
  <section class="dock card" :class="{ 'dock--collapsed': collapsed }" aria-label="Terminais dos repositórios">
    <header class="dock__bar">
      <button type="button" class="dock__toggle" :aria-expanded="!collapsed" @click="emit('toggle')">
        <SquareTerminal :size="14" />
        Terminais
        <span v-if="sessions.length" class="dock__count">{{ sessions.length }}</span>
        <ChevronDown v-if="!collapsed" :size="14" />
        <ChevronUp v-else :size="14" />
      </button>

      <template v-if="store.available !== false">
        <button
          v-if="selected"
          type="button"
          class="dock__new"
          :disabled="store.opening"
          :title="`Novo terminal em ${selected.path}`"
          @click="openIn(selected)"
        >
          <Plus :size="13" /> {{ selected.slug }}
        </button>
        <select v-if="extraRepos.length" v-model="adding" class="dock__other" aria-label="Terminal em outro repositório" @change="openOther">
          <option value="">Terminal em outro repo…</option>
          <option v-for="repo in extraRepos" :key="repo.slug" :value="repo.slug">{{ repo.slug }}</option>
        </select>
      </template>

      <span v-if="store.error" class="dock__error" role="alert">{{ store.error }}</span>
      <span v-else-if="store.available && !store.connected && sessions.length" class="dock__muted">reconectando…</span>
    </header>

    <div v-if="!collapsed" class="dock__body">
      <div v-if="store.available === false" class="dock__empty">
        <p>
          O terminal do SprintAI não está no ar (porta 8766). Rode o atalho <strong>SprintAI</strong> de novo — ele
          sobe o terminal junto — ou abra a pasta no Windows Terminal.
        </p>
        <button v-if="selected" type="button" class="btn btn--secondary" @click="emit('open-folder', 'terminal', selected.path)">
          <SquareTerminal :size="14" /> Abrir {{ selected.slug }} no Windows Terminal
        </button>
      </div>

      <div v-else-if="!sessions.length" class="dock__empty">
        <p>Nenhum terminal aberto nos repositórios deste workspace.</p>
        <div class="dock__starters">
          <button v-for="repo in repos" :key="repo.slug" type="button" class="btn btn--secondary" :disabled="store.opening" @click="openIn(repo)">
            <SquareTerminal :size="14" /> {{ repo.slug }}
          </button>
        </div>
      </div>

      <template v-else>
        <nav v-if="tabbed" class="dock__tabs" role="tablist">
          <button
            v-for="session in sessions"
            :key="session.id"
            type="button"
            role="tab"
            class="dock__tab"
            :class="{ 'dock__tab--active': session.id === activeId }"
            :aria-selected="session.id === activeId"
            @click="activeId = session.id"
          >
            {{ session.label }}
          </button>
        </nav>

        <div class="dock__panes" :style="{ '--panes': tabbed ? 1 : sessions.length }">
          <article
            v-for="session in sessions"
            v-show="!tabbed || session.id === activeId"
            :key="session.id"
            class="term"
            :class="{
              'term--active': session.id === activeId,
              'term--dead': !session.alive,
              'term--focus': focusRepos.includes(repoOf(session)?.slug),
            }"
            :data-session="session.id"
            @focusin="activeId = session.id"
          >
            <header class="term__bar">
              <strong class="term__label">{{ repoOf(session)?.slug ?? session.label }}</strong>
              <code class="term__cwd" :title="session.cwd">{{ session.cwd }}</code>
              <span class="term__state" :data-alive="session.alive">{{ session.alive ? 'Ativo' : `Encerrado${session.exit_code != null ? ` (${session.exit_code})` : ''}` }}</span>
              <button v-if="!session.alive" type="button" class="term__action" title="Abrir de novo na mesma pasta" aria-label="Reabrir" @click="store.reopen(session.id)">
                <RotateCcw :size="13" />
              </button>
              <button type="button" class="term__action" title="Abrir a pasta no Windows Terminal" aria-label="Windows Terminal" @click="emit('open-folder', 'terminal', session.cwd)">
                <SquareTerminal :size="13" />
              </button>
              <button type="button" class="term__action" title="Fechar o terminal (encerra o shell e o que estiver rodando nele)" aria-label="Fechar terminal" @click="closeSession(session)">
                <X :size="13" />
              </button>
            </header>
            <TerminalPane class="term__pane" :session="session" :active="!tabbed || session.id === activeId" />
          </article>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.dock {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.dock__bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px var(--space-3);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--text-xs);
}

.dock--collapsed .dock__bar {
  border-bottom: 0;
}

.dock__toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  border: 0;
  background: none;
  color: var(--color-text);
  font-size: var(--text-sm);
  font-weight: 600;
}

.dock__count {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-accent-surface);
  color: var(--color-accent-text);
  font-size: 11px;
}

.dock__new {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.dock__new:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.dock__other {
  padding: 3px 6px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.dock__error {
  margin-left: auto;
  color: var(--color-error);
}

.dock__muted {
  margin-left: auto;
  color: var(--color-text-muted);
}

.dock__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.dock__empty {
  padding: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.dock__empty p {
  margin: 0 0 var(--space-3);
}

.dock__starters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.dock__tabs {
  display: flex;
  gap: 2px;
  padding: 4px var(--space-2) 0;
}

.dock__tab {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-bottom: 0;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.dock__tab--active {
  background: var(--term-bg);
  color: var(--color-text);
}

.dock__panes {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(var(--panes), minmax(0, 1fr));
  gap: var(--space-2);
  padding: var(--space-2);
}

.term {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--term-bg);
}

.term--active {
  border-color: var(--color-primary);
}

.term--focus .term__bar {
  background: var(--color-primary-soft);
}

.term__bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px 6px 4px 10px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface);
  font-size: 11px;
}

.term__label {
  font-size: var(--text-xs);
}

.term__cwd {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-muted);
}

.term__state {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-success-surface);
  color: var(--color-success-text);
}

.term__state[data-alive='false'] {
  background: var(--color-neutral-surface);
  color: var(--color-neutral-text);
}

.term__action {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.term__action:hover {
  background: var(--color-surface-hover);
  color: var(--color-primary);
}

.term__pane {
  flex: 1;
  min-height: 0;
}

.term--dead .term__pane {
  opacity: 0.7;
}
</style>
