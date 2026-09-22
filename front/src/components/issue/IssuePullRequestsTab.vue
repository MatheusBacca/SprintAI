<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  GitBranch,
  MessageSquare,
  RefreshCw,
  TriangleAlert,
  X,
} from 'lucide-vue-next'
import ActivityKindIcon from '@/components/activity/ActivityKindIcon.vue'
import MarkdownRenderer from '@/components/issue/MarkdownRenderer.js'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { activityKindMeta } from '@/constants/activityKinds'
import { prKey, useIssueDetailStore } from '@/stores/issueDetail'
import { useRefreshStore } from '@/stores/refresh'
import { copyRichText } from '@/utils/clipboard'
import { safeUrl } from '@/utils/safeUrl'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  summary: { type: Object, required: true },
})

const BUILD_LABEL = { SUCCESSFUL: 'Build ok', FAILED: 'Build falhou', STOPPED: 'Build parado', INPROGRESS: 'Build rodando' }
const COPY_FEEDBACK_MS = 2000

const store = useIssueDetailStore()
const refresh = useRefreshStore()

const pullRequests = computed(() => props.summary.repos.flatMap((repo) => repo.pull_requests))

function timelineOf(pr) {
  return store.prTimelines[prKey(pr.repo_slug, pr.id)] ?? { data: null, loading: false, error: null }
}

// O histórico fica aberto: é ele que se quer ver ao entrar na aba, e o store
// guarda o que já veio, então trocar de tarefa e voltar não repete a busca.
function loadAll() {
  for (const pr of pullRequests.value) store.loadPrTimeline(pr.repo_slug, pr.id)
}
onMounted(loadAll)
watch(() => props.summary, loadAll)
// Sync ou "Recarregar": a review nova aparece sem fechar e reabrir a aba.
watch(() => refresh.revision, loadAll)

/** Texto do evento: o mesmo vocabulário do feed da Home, sem repetir o nome de quem fez. */
function eventText(entry) {
  if (entry.kind === 'pr_commit') {
    return entry.after_changes_requested ? 'subiu a correção' : 'subiu commit'
  }
  return activityKindMeta(entry.kind).text.replace(/ no PR$| o PR$/, '')
}

function inlineRef(entry) {
  if (!entry.inline_path) return null
  return entry.inline_to ? `${entry.inline_path}:${entry.inline_to}` : entry.inline_path
}

const copyState = ref(null)

/** HTML renderizado para colar formatado; o markdown original como texto puro. */
async function copyComment(entry, event) {
  const rendered = event.currentTarget.closest('.tl__comment')?.querySelector('.md')
  const ok = await copyRichText({ html: rendered?.innerHTML ?? null, text: entry.body ?? '' })
  setCopyState(entry.comment_id, ok)
}

function setCopyState(id, ok) {
  copyState.value = { id, ok }
  setTimeout(() => {
    if (copyState.value?.id === id) copyState.value = null
  }, COPY_FEEDBACK_MS)
}

function copyLabel(entry) {
  if (copyState.value?.id !== entry.comment_id) return 'Copiar o comentário'
  return copyState.value.ok ? 'Copiado' : 'Não deu para copiar'
}

// Review minimizada, por PR. Tarefa com vários PRs vira uma rolagem só; minimizar o
// que já foi lido deixa os outros à vista. O padrão continua aberto — é o histórico
// que se quer ver ao entrar na aba.
const collapsed = ref({})

function isOpen(pr) {
  return !collapsed.value[prKey(pr.repo_slug, pr.id)]
}

function toggle(pr) {
  const key = prKey(pr.repo_slug, pr.id)
  collapsed.value = { ...collapsed.value, [key]: isOpen(pr) }
}

function reviewCount(pr) {
  const entries = timelineOf(pr).data?.entries
  if (!entries) return null
  return entries.length === 1 ? '1 atualização' : `${entries.length} atualizações`
}
</script>

<template>
  <div class="prs">
    <p v-if="!summary.repos.length" class="prs__empty">
      Nenhum PR ou branch com a chave {{ summary.issue_key }} nos repositórios sincronizados.
    </p>

    <article v-for="repo in summary.repos" :key="repo.repo_slug" class="prs__repo">
      <header class="prs__repo-header">
        <strong>{{ repo.repo_slug }}</strong>
        <PrStatusBadge :status="repo.status" size="sm" />
      </header>

      <ul class="prs__list">
        <li v-for="pr in repo.pull_requests" :key="pr.id" class="pr">
          <div class="pr__top">
            <a v-if="safeUrl(pr.url)" :href="safeUrl(pr.url)" target="_blank" rel="noopener noreferrer" class="pr__title">
              #{{ pr.id }} {{ pr.title }} <ExternalLink :size="11" />
            </a>
            <span v-else class="pr__title">#{{ pr.id }} {{ pr.title }}</span>
            <PrStatusBadge :status="pr.status" size="sm" />
          </div>

          <div class="pr__branch">
            <span class="pr__branch-name"><GitBranch :size="12" /> {{ pr.source_branch }} → {{ pr.destination_branch }}</span>
            <span v-if="pr.match === 'title'" class="pr__match" title="A chave aparece só no título do PR">citada no título</span>
          </div>

          <div class="pr__meta">
            <span v-if="pr.approvals" class="pr__ok"><Check :size="12" /> {{ pr.approvals }} aprovação(ões)</span>
            <span v-if="pr.changes_requested" class="pr__changes"><X :size="12" /> {{ pr.changes_requested }} pedido(s) de ajuste</span>
            <!-- O Bitbucket mantém o pedido do revisor até ele mexer de novo; isto conta o outro lado. -->
            <span v-if="pr.fix_pushed" class="pr__ok" title="Entrou commit depois do último pedido de ajuste">
              <Check :size="12" /> correção enviada
            </span>
            <span v-if="pr.comment_count"><MessageSquare :size="12" /> {{ pr.comment_count }}</span>
            <span v-if="pr.build_status" :class="{ pr__fail: pr.build_failed }">
              <TriangleAlert v-if="pr.build_failed" :size="12" /> {{ BUILD_LABEL[pr.build_status] ?? pr.build_status }}
            </span>
            <span class="pr__when">{{ formatRelative(pr.updated_on) }}</span>
          </div>

          <ul v-if="pr.reviewers.length" class="pr__reviewers">
            <li
              v-for="(r, i) in pr.reviewers"
              :key="i"
              :data-state="r.approved ? 'approved' : r.state || 'pending'"
              :title="r.approved ? 'Aprovou' : r.state === 'changes_requested' ? 'Pediu ajustes' : 'Aguardando'"
            >
              {{ r.name ?? 'Revisor' }}
            </li>
          </ul>

          <div class="tl">
            <button
              type="button"
              class="tl__toggle"
              :aria-expanded="isOpen(pr) ? 'true' : 'false'"
              :title="isOpen(pr) ? 'Minimizar a review' : 'Abrir a review'"
              @click="toggle(pr)"
            >
              <ChevronDown v-if="isOpen(pr)" :size="14" />
              <ChevronRight v-else :size="14" />
              Review
              <span v-if="reviewCount(pr)" class="tl__count">{{ reviewCount(pr) }}</span>
            </button>

            <!-- Fica fora do que se minimiza: é o aviso que faz abrir a review de novo. -->
            <p v-if="timelineOf(pr).data?.pending_review" class="tl__pending">
              <TriangleAlert :size="13" /> Ajuste pedido e ainda sem commit depois dele.
            </p>

            <template v-if="isOpen(pr)">
              <p v-if="timelineOf(pr).loading" class="tl__note">
                <RefreshCw :size="13" class="spin" /> Carregando o histórico…
              </p>
              <p v-else-if="timelineOf(pr).error" class="tl__note tl__note--error" role="alert">
                {{ timelineOf(pr).error }}
                <button type="button" class="btn btn--secondary" @click="store.loadPrTimeline(pr.repo_slug, pr.id, { force: true })">
                  Tentar de novo
                </button>
              </p>
              <template v-else-if="timelineOf(pr).data">
                <p v-if="timelineOf(pr).data.request_before_history" class="tl__note">
                  O pedido de ajuste é anterior ao histórico local — a marcação de correção
                  vale a partir do próximo.
                </p>

                <ol v-if="timelineOf(pr).data.entries.length" class="tl__list">
                  <li
                    v-for="(entry, i) in timelineOf(pr).data.entries"
                    :key="i"
                    class="tl__item"
                    :data-kind="entry.kind"
                    :data-fix="entry.after_changes_requested || undefined"
                  >
                    <span class="tl__icon">
                      <MessageSquare v-if="entry.kind === 'comment'" :size="13" />
                      <ActivityKindIcon v-else :kind="entry.kind" :size="13" />
                    </span>
  
                    <!-- Comentário vira cartão; evento é uma linha só, como no Bitbucket. -->
                    <div v-if="entry.kind === 'comment'" class="tl__comment">
                      <p class="tl__head">
                        <strong>{{ entry.actor_name ?? 'Alguém' }}</strong>
                        <span v-if="inlineRef(entry)" class="tl__file">{{ inlineRef(entry) }}</span>
                        <time class="tl__when" :datetime="entry.at">{{ formatRelative(entry.at) }}</time>
                        <button
                          v-if="!entry.is_deleted"
                          type="button"
                          class="tl__copy"
                          :class="{ 'tl__copy--ok': copyState?.id === entry.comment_id && copyState.ok }"
                          :title="copyLabel(entry)"
                          :aria-label="copyLabel(entry)"
                          @click="copyComment(entry, $event)"
                        >
                          <Check v-if="copyState?.id === entry.comment_id && copyState.ok" :size="13" />
                          <Copy v-else :size="13" />
                        </button>
                      </p>
                      <p v-if="entry.is_deleted" class="tl__gone">comentário apagado no Bitbucket</p>
                      <!-- VNodes, nunca v-html: o corpo vem do Bitbucket, é dado de terceiro. -->
                      <MarkdownRenderer v-else :source="entry.body ?? ''" />
                    </div>
  
                    <p v-else class="tl__head tl__head--event">
                      <strong>{{ entry.actor_name ?? 'Alguém' }}</strong>
                      <span class="tl__what">{{ eventText(entry) }}</span>
                      <span v-if="entry.commit" class="tl__commit">{{ entry.commit.slice(0, 7) }}</span>
                      <time class="tl__when" :datetime="entry.at">{{ formatRelative(entry.at) }}</time>
                    </p>
                  </li>
                </ol>
                <p v-else class="tl__note">
                  Nada no histórico ainda. Ele é preenchido durante a sincronização.
                </p>
              </template>
            </template>
          </div>
        </li>
      </ul>

      <ul v-if="repo.branches.length" class="prs__list">
        <li v-for="b in repo.branches" :key="b.name" class="pr pr--branch" :class="{ 'pr--stale': b.stale }">
          <div class="pr__branch">
            <span class="pr__branch-name"><GitBranch :size="12" /> {{ b.name }}</span>
            <span class="pr__match">{{ b.stale ? 'sobra de merge' : 'sem PR' }}</span>
          </div>
          <div class="pr__meta"><span class="pr__when">último commit {{ formatRelative(b.target_date) }}</span></div>
        </li>
      </ul>
    </article>
  </div>
</template>

<style scoped>
.prs {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.prs__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.prs__repo {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.prs__repo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-muted);
  font-size: var(--text-sm);
}

.prs__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.pr {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--space-3);
  font-size: var(--text-sm);
}

.pr + .pr,
.prs__list + .prs__list .pr:first-child {
  border-top: 1px solid var(--color-border);
}

.pr--stale {
  opacity: 0.65;
}

.pr__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.pr__title {
  font-weight: 600;
  color: var(--color-text);
}

a.pr__title:hover {
  color: var(--color-primary);
}

.pr__branch,
.pr__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.pr__branch-name {
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}

.pr__branch-name svg {
  vertical-align: -2px;
}

.pr__meta span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.pr__match {
  padding: 0 5px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  font-family: var(--font-sans);
}

.pr__ok {
  color: var(--color-success);
}

.pr__changes,
.pr__fail {
  color: var(--color-warning);
}

.pr__fail {
  color: var(--color-error);
}

.pr__when {
  margin-left: auto;
  color: var(--color-text-muted);
}

.pr__reviewers {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 2px 0 0;
  padding: 0;
  list-style: none;
}

.pr__reviewers li {
  padding: 1px 8px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.pr__reviewers li[data-state='approved'] {
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.pr__reviewers li[data-state='changes_requested'] {
  border-color: var(--color-warning-border);
  color: var(--color-warning);
}

/* Histórico da PR ------------------------------------------------------------- */

.tl {
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
}

.tl__toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  margin-bottom: var(--space-2);
  padding: 2px 0;
  border: 0;
  background: none;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.tl__toggle:hover {
  color: var(--color-text);
}

.tl__count {
  font-weight: 400;
  color: var(--color-text-muted);
}

.tl__note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.tl__note--error {
  color: var(--color-error);
}

.tl__pending {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
  font-size: var(--text-xs);
  font-weight: 600;
}

/*
 * Linha do tempo no formato do Bitbucket: um trilho vertical passando por dentro
 * dos marcadores. O trilho é um ::before do <ol> — desenhá-lo por item deixaria
 * emendas visíveis entre as linhas.
 */
.tl__list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}

.tl__list::before {
  content: '';
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 10px;
  width: 1px;
  background: var(--color-border-strong);
}

.tl__item {
  position: relative;
  display: flex;
  gap: var(--space-3);
}

.tl__icon {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 21px;
  height: 21px;
  border: 1px solid var(--color-border-strong);
  border-radius: 50%;
  /* Opaco de propósito: é ele que "corta" o trilho por baixo. */
  background: var(--color-surface);
  color: var(--color-text-muted);
}

.tl__item[data-kind='comment'] .tl__icon {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* O commit que responde ao último pedido de ajuste — é o que se procura na aba. */
.tl__item[data-fix] .tl__icon {
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.tl__item[data-fix] .tl__what {
  color: var(--color-success);
  font-weight: 600;
}

.tl__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px var(--space-2);
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.tl__head--event {
  flex: 1;
  min-width: 0;
  /* Alinha o texto do evento com o meio do marcador redondo. */
  padding-top: 3px;
}

.tl__head strong {
  color: var(--color-text);
}

.tl__commit,
.tl__file {
  padding: 0 5px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.tl__when {
  margin-left: auto;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.tl__comment {
  flex: 1;
  min-width: 0;
  padding: var(--space-2) var(--space-3) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.tl__copy {
  flex-shrink: 0;
  display: inline-flex;
  padding: 3px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.tl__copy:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.tl__copy--ok {
  color: var(--color-success);
}

.tl__gone {
  margin: 4px 0 0;
  font-size: var(--text-sm);
  font-style: italic;
  color: var(--color-text-muted);
}

/* Markdown do comentário ------------------------------------------------------- */

.tl__comment :deep(.md) {
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  line-height: 20px;
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.tl__comment :deep(.md > :first-child) {
  margin-top: 0;
}

.tl__comment :deep(.md > :last-child) {
  margin-bottom: 0;
}

.tl__comment :deep(.md p) {
  margin: 0 0 var(--space-2);
}

.tl__comment :deep(.md-heading) {
  margin: var(--space-3) 0 var(--space-2);
  font-family: var(--font-sans);
  font-size: var(--text-md);
  font-weight: 600;
  line-height: 20px;
  letter-spacing: 0;
}

.tl__comment :deep(.md-list) {
  margin: 0 0 var(--space-2);
  padding-left: var(--space-5);
}

.tl__comment :deep(.md-list li) {
  margin-bottom: 2px;
}

.tl__comment :deep(.md-list .md-list) {
  margin-bottom: 0;
}

.tl__comment :deep(.md-code) {
  padding: 1px 4px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.tl__comment :deep(.md-pre) {
  margin: 0 0 var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
  overflow-x: auto;
}

.tl__comment :deep(.md-pre code) {
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre;
}

.tl__comment :deep(.md-quote) {
  margin: 0 0 var(--space-2);
  padding-left: var(--space-3);
  border-left: 3px solid var(--color-border-strong);
  color: var(--color-text-secondary);
}

.tl__comment :deep(.md-rule) {
  margin: var(--space-3) 0;
  border: 0;
  border-top: 1px solid var(--color-border);
}

.tl__comment :deep(.md a) {
  color: var(--color-primary);
  text-decoration: underline;
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
