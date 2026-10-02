<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowDown, ArrowDownToLine, ArrowUp, FolderGit2, GitBranch, Globe, Tag, Trash2 } from 'lucide-vue-next'
import IssueKeyChip from './IssueKeyChip.vue'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { useRepoTimelineStore } from '@/stores/repoTimeline'
import { normalize } from '@/utils/highlight'
import { formatRelative } from '@/utils/time'

/**
 * Painel de branches da linha do tempo: as locais, as do `origin` e as tags do repo, e — com
 * texto na busca — os commits do histórico inteiro que casam com ele.
 *
 * Duas ações por branch local, as duas só fast-forward ou com confirmação:
 * - **Avançar** até o upstream, quando ela está atrás e o upstream existe;
 * - **Apagar** (local), com o segundo clique confirmando. Se ela tem commit que não está em
 *   outra branch, o git recusa e o painel pergunta de novo — o terceiro clique vai com `-D`.
 *
 * Branch no Bitbucket não se apaga daqui.
 */
const props = defineProps({
  selectedSha: { type: String, default: null },
  baseBranch: { type: String, default: null },
})
const emit = defineEmits(['open-issue'])

const store = useRepoTimelineStore()
const PAGE = 60

const needle = computed(() => normalize(store.query.trim()))
function matches(item) {
  if (!needle.value) return true
  return normalize(`${item.name} ${item.subject ?? ''}`).includes(needle.value)
}

const groups = computed(() => {
  const refs = store.panel.refs.filter(matches)
  return [
    { id: 'local', label: 'Locais', icon: GitBranch, items: refs.filter((r) => r.kind === 'local') },
    { id: 'remote', label: 'Remotas (origin)', icon: Globe, items: refs.filter((r) => r.kind === 'remote') },
    { id: 'tag', label: 'Tags', icon: Tag, items: refs.filter((r) => r.kind === 'tag') },
  ]
})

const shown = ref({ local: PAGE, remote: PAGE, tag: PAGE })
const collapsed = ref({ local: false, remote: true, tag: true })
// Com busca, tudo abre: o que casou não pode ficar escondido num grupo fechado.
watch(needle, (value) => {
  if (value) collapsed.value = { local: false, remote: false, tag: false }
})

const commits = computed(() => (needle.value.length >= 2 ? store.searchResults?.commits ?? [] : []))

// --- Apagar com confirmação ---------------------------------------------------------------

/** `{ name, force }` — a branch esperando o próximo clique. */
const confirming = ref(null)

function canDelete(item) {
  return item.kind === 'local' && !item.worktree && item.name !== props.baseBranch
}

function deleteTitle(item) {
  if (item.worktree) return 'Aberta numa worktree — troque de branch lá antes'
  if (item.name === props.baseBranch) return 'A branch base não se apaga por aqui'
  if (confirming.value?.name === item.name) {
    return confirming.value.force ? 'Clique de novo para apagar mesmo assim (perde os commits só dela)' : 'Clique de novo para apagar'
  }
  return 'Apagar a branch local (o Bitbucket não é tocado)'
}

async function onDelete(item) {
  if (!canDelete(item)) return
  if (confirming.value?.name !== item.name) {
    confirming.value = { name: item.name, force: false }
    return
  }
  const force = confirming.value.force
  const result = await store.deleteBranch(item.name, { force })
  // O `-d` recusou por ter commit só nela: o próximo clique vai com `-D`.
  confirming.value = !result.ok && result.code === 'unmerged' && !force ? { name: item.name, force: true } : null
}

function canUpdate(item) {
  return item.kind === 'local' && item.behind > 0 && item.upstream && !item.gone
}

function updateTitle(item) {
  return item.worktree
    ? `Avançar ${item.behind} commit(s) até ${item.upstream} — fast-forward na worktree aberta (os arquivos dela mudam)`
    : `Avançar ${item.behind} commit(s) até ${item.upstream} — fast-forward, só a ref anda`
}
</script>

<template>
  <aside class="panel" aria-label="Branches e tags do repositório">
    <p v-if="store.feedback" class="panel__feedback" :data-type="store.feedback.type" role="status">
      {{ store.feedback.text }}
    </p>
    <p v-if="store.panel.error" class="panel__error" role="alert">{{ store.panel.error }}</p>
    <p v-else-if="!store.panel.loaded" class="panel__muted">Lendo as branches…</p>

    <template v-else>
      <section v-if="needle.length >= 2" class="group" data-group="commits">
        <header class="group__head">
          <span>Commits</span>
          <span class="group__count">{{ store.searching ? '…' : commits.length }}</span>
        </header>
        <p v-if="store.searchResults?.error" class="panel__error">{{ store.searchResults.error }}</p>
        <p v-else-if="!store.searching && !commits.length" class="panel__muted">Nenhum commit com esse texto.</p>
        <ul class="group__list">
          <li
            v-for="commit in commits"
            :key="commit.sha"
            class="item item--commit"
            :class="{ 'item--active': commit.sha === selectedSha }"
            :data-sha="commit.sha"
          >
            <button type="button" class="item__main" :title="commit.subject" @click="store.focusCommit(commit.sha)">
              <code class="item__sha">{{ commit.sha.slice(0, 7) }}</code>
              <span class="item__name">{{ commit.subject }}</span>
            </button>
            <span class="item__meta">
              <IssueKeyChip
                v-for="key in commit.issue_keys"
                :key="key"
                :issue-key="key"
                :status="store.issueStatus[key]"
                @open="emit('open-issue', $event)"
              />
              {{ commit.author }} · {{ formatRelative(commit.committed_at) }}
            </span>
          </li>
        </ul>
      </section>

      <section v-for="group in groups" :key="group.id" class="group" :data-group="group.id">
        <button type="button" class="group__head group__head--toggle" :aria-expanded="!collapsed[group.id]" @click="collapsed[group.id] = !collapsed[group.id]">
          <component :is="group.icon" :size="12" />
          <span>{{ group.label }}</span>
          <span class="group__count">{{ group.items.length }}</span>
        </button>
        <ul v-if="!collapsed[group.id]" class="group__list">
          <li
            v-for="item in group.items.slice(0, shown[group.id])"
            :key="`${item.kind}:${item.name}`"
            class="item"
            :class="{
              'item--active': item.target === selectedSha,
              'item--feature': item.in_feature,
              'item--tag': item.kind === 'tag',
              'item--busy': store.busyBranch === item.name,
            }"
            :data-ref="item.name"
          >
            <button type="button" class="item__main" :title="item.subject ?? item.name" @click="store.focusCommit(item.target)">
              <span v-if="item.is_head" class="item__head">HEAD</span>
              <span class="item__name">{{ item.name }}</span>
              <span v-if="item.worktree && !item.is_head" class="item__icon" :title="`Aberta na worktree ${item.worktree}`">
                <FolderGit2 :size="11" />
              </span>
              <span v-if="item.ahead" class="item__track" :title="`${item.ahead} commit(s) para enviar`"><ArrowUp :size="10" />{{ item.ahead }}</span>
              <span v-if="item.behind" class="item__track" :title="`${item.behind} commit(s) para trazer`"><ArrowDown :size="10" />{{ item.behind }}</span>
              <span v-if="item.gone" class="item__gone" title="A branch foi apagada no Bitbucket">apagada no remoto</span>
            </button>
            <PrStatusBadge
              v-if="item.pull_requests?.length && item.kind === 'local'"
              :status="item.pull_requests[0].status"
              :pr-count="item.pull_requests.length"
              :links="item.pull_requests"
              :review="item.pull_requests[0].review"
              size="sm"
            />
            <span class="item__date">{{ formatRelative(item.committed_at) }}</span>
            <span v-if="item.kind === 'local'" class="item__actions">
              <button
                v-if="canUpdate(item)"
                type="button"
                class="item__action"
                :disabled="store.busyBranch === item.name"
                :title="updateTitle(item)"
                aria-label="Avançar até o upstream"
                @click="store.updateBranch(item.name)"
              >
                <ArrowDownToLine :size="12" />
              </button>
              <button
                type="button"
                class="item__action item__action--danger"
                :class="{ 'item__action--confirm': confirming?.name === item.name }"
                :disabled="!canDelete(item) || store.busyBranch === item.name"
                :title="deleteTitle(item)"
                :aria-label="confirming?.name === item.name ? 'Confirmar: apagar a branch local' : 'Apagar a branch local'"
                @click="onDelete(item)"
                @blur="confirming?.name === item.name && !confirming.force ? (confirming = null) : null"
              >
                <Trash2 :size="12" />
                <span v-if="confirming?.name === item.name">{{ confirming.force ? 'Mesmo assim?' : 'Apagar?' }}</span>
              </button>
            </span>
          </li>
        </ul>
        <button
          v-if="!collapsed[group.id] && group.items.length > shown[group.id]"
          type="button"
          class="group__more"
          @click="shown[group.id] += PAGE * 3"
        >
          Mostrar mais ({{ group.items.length - shown[group.id] }})
        </button>
      </section>
    </template>
  </aside>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 300px;
  min-height: 0;
  padding: var(--space-2) var(--space-2) var(--space-3);
  overflow: auto;
  border-right: 1px solid var(--color-border);
  font-size: var(--text-xs);
}

.panel__feedback,
.panel__error,
.panel__muted {
  margin: 0;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
}

.panel__feedback[data-type='success'] {
  background: var(--color-success-surface);
  color: var(--color-success-text);
}

.panel__feedback[data-type='error'],
.panel__error {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.group__head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 6px;
  border: 0;
  background: none;
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-align: left;
  text-transform: uppercase;
}

.group__head--toggle:hover {
  color: var(--color-text);
}

.group__count {
  margin-left: auto;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-surface-muted);
  font-weight: 500;
  text-transform: none;
}

.group__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.group__more {
  margin: 2px 6px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-primary);
  font-size: 11px;
}

.item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 1px 4px 1px 0;
  border-radius: var(--radius-sm);
}

.item:hover,
.item--active {
  background: var(--color-surface-hover);
}

.item--active {
  box-shadow: inset 2px 0 0 var(--color-primary);
}

.item--busy {
  opacity: 0.6;
}

.item--commit {
  flex-direction: column;
  align-items: stretch;
  padding: 3px 4px;
}

.item__main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border: 0;
  background: none;
  color: var(--color-text);
  font-size: var(--text-xs);
  text-align: left;
}

.item__name {
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item--commit .item__name {
  font-family: inherit;
}

.item--feature .item__name {
  color: var(--color-primary);
  font-weight: 600;
}

.item--tag .item__name {
  padding: 0 5px;
  border: 1px solid var(--git-tag-border);
  border-radius: var(--radius-sm);
  background: var(--git-tag-bg);
  color: var(--git-tag-text);
  font-weight: 600;
}

.item__head {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: var(--color-primary);
}

.item__sha {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.item__icon,
.item__track {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  color: var(--color-text-secondary);
}

.item__gone {
  flex-shrink: 0;
  color: var(--color-warning-text);
}

.item__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  color: var(--color-text-muted);
}

.item__date {
  flex-shrink: 0;
  color: var(--color-text-muted);
  font-size: 10px;
}

.item__actions {
  flex-shrink: 0;
  display: inline-flex;
  gap: 2px;
}

.item__action {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 22px;
  padding: 0 5px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
  font-size: 11px;
}

.item__action:not(:disabled):hover {
  background: var(--color-surface);
  color: var(--color-primary);
}

.item__action--danger:not(:disabled):hover,
.item__action--confirm {
  color: var(--color-error);
}

.item__action--confirm {
  background: var(--color-error-surface);
}

.item__action:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
