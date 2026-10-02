<script setup>
import { computed, onMounted, reactive, watch } from 'vue'
import { FolderGit2, RefreshCw } from 'lucide-vue-next'
import { useWorkspaceReposStore } from '@/stores/workspaceRepos'

/**
 * Configurações › Workspace: as pastas de `C:\projects` e o vínculo de cada uma com o
 * Bitbucket. O automático acerta quase sempre (remote `origin` + branch principal do
 * Bitbucket); o ajuste daqui é para o clone com nome diferente ou a base fora do padrão.
 */
const store = useWorkspaceReposStore()

const BASE_SOURCES = {
  manual: 'definida aqui',
  bitbucket: 'do Bitbucket',
  origin: 'do origin/HEAD do clone',
  local: 'palpite pelas branches do clone',
}

// Rascunho por repositório: a linha só manda o PUT quando algo mudou nela.
const drafts = reactive({})

function draftFrom(repo) {
  return {
    link: repo.link,
    bbSlug: repo.link === 'manual' ? repo.bb_slug ?? '' : '',
    baseBranch: repo.base_source === 'manual' ? repo.base_branch ?? '' : '',
  }
}

function reset(repo) {
  drafts[repo.slug] = draftFrom(repo)
}

watch(
  () => store.repos,
  (repos) => repos.forEach(reset),
  { immediate: true },
)

onMounted(() => store.load())

const rows = computed(() => store.repos.filter((repo) => repo.present || repo.link !== 'auto'))

function dirty(repo) {
  const draft = drafts[repo.slug]
  if (!draft) return false
  const saved = draftFrom(repo)
  return (
    draft.link !== saved.link ||
    (draft.link === 'manual' && draft.bbSlug.trim() !== saved.bbSlug) ||
    draft.baseBranch.trim() !== saved.baseBranch
  )
}

function automaticLink(repo) {
  if (repo.link === 'auto') return repo.bb_slug ? `Automático (${repo.bb_slug})` : 'Automático (nenhum)'
  return 'Automático'
}

function basePlaceholder(repo) {
  if (repo.base_source && repo.base_source !== 'manual') return repo.base_branch
  return 'automática'
}

async function save(repo) {
  const draft = drafts[repo.slug]
  await store.update(repo.slug, {
    link: draft.link,
    bbSlug: draft.bbSlug.trim(),
    baseBranch: draft.baseBranch.trim(),
  })
}
</script>

<template>
  <section class="repos card">
    <header class="repos__header">
      <FolderGit2 :size="18" />
      <div>
        <h2 class="repos__title">Repositórios locais</h2>
        <p class="repos__desc">
          As pastas de <code>{{ store.root ?? 'C:\\projects' }}</code>, lidas do disco agora — sem rodar
          git e sem sair dessa pasta. O vínculo com o Bitbucket sai do remote <code>origin</code>; a
          branch base, da branch principal no Bitbucket ou do próprio clone. Ajuste aqui só quando o
          automático errar.
        </p>
      </div>
      <button
        type="button"
        class="btn btn--secondary repos__reload"
        :disabled="store.loading"
        title="Ler as pastas de novo"
        @click="store.load()"
      >
        <RefreshCw :size="14" :class="{ spin: store.loading }" />
        Ler de novo
      </button>
    </header>

    <p v-if="store.error" class="repos__error" role="alert">{{ store.error }}</p>
    <p v-else-if="!store.loaded" class="repos__muted">Lendo as pastas…</p>

    <table v-else class="repos__table">
      <thead>
        <tr>
          <th>Pasta</th>
          <th>Bitbucket</th>
          <th>Branch base</th>
          <th>Branch atual</th>
          <th aria-label="Ações" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="repo in rows" :key="repo.slug" class="row" :data-repo="repo.slug">
          <td>
            <div class="row__name">
              <strong>{{ repo.slug }}</strong>
              <span v-if="!repo.present" class="pill pill--warning">pasta sumiu</span>
              <span v-else-if="!repo.has_git" class="pill">sem git</span>
            </div>
            <code class="row__path" :title="repo.remote_url ?? 'sem remote origin'">{{ repo.path }}</code>
          </td>
          <td>
            <div v-if="drafts[repo.slug]" class="row__link">
              <select
                v-model="drafts[repo.slug].link"
                class="field__input row__select"
                :disabled="!repo.has_git"
                aria-label="Vínculo com o Bitbucket"
              >
                <option value="auto">{{ automaticLink(repo) }}</option>
                <option value="none">Sem vínculo</option>
                <option value="manual">Outro repositório…</option>
              </select>
              <input
                v-if="drafts[repo.slug].link === 'manual'"
                v-model="drafts[repo.slug].bbSlug"
                class="field__input row__slug"
                placeholder="slug no Bitbucket"
                aria-label="Repositório do Bitbucket"
              >
              <span v-if="repo.in_mirror" class="pill pill--success" title="Está em Sincronização: tem PR e branch no espelho">
                no espelho
              </span>
            </div>
          </td>
          <td>
            <input
              v-if="drafts[repo.slug]"
              v-model="drafts[repo.slug].baseBranch"
              class="field__input row__base"
              :placeholder="basePlaceholder(repo)"
              :disabled="!repo.has_git"
              aria-label="Branch base"
            >
            <span v-if="repo.base_source" class="field__hint">{{ BASE_SOURCES[repo.base_source] }}</span>
          </td>
          <td>
            <code v-if="repo.current_branch" class="row__branch">{{ repo.current_branch }}</code>
            <span v-else-if="repo.detached" class="muted">HEAD destacado</span>
            <span v-else class="muted">—</span>
          </td>
          <td class="row__actions">
            <template v-if="dirty(repo)">
              <button type="button" class="btn btn--secondary" @click="reset(repo)">Descartar</button>
              <button
                type="button"
                class="btn btn--primary"
                :disabled="store.savingSlug === repo.slug"
                @click="save(repo)"
              >
                {{ store.savingSlug === repo.slug ? 'Salvando…' : 'Salvar' }}
              </button>
            </template>
            <p
              v-else-if="store.feedback?.slug === repo.slug"
              class="row__feedback"
              :data-type="store.feedback.type"
              role="status"
            >
              {{ store.feedback.text }}
            </p>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.repos {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.repos__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

.repos__header > svg {
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--color-primary);
}

.repos__title {
  margin: 0 0 4px;
  font-size: var(--text-md);
  font-weight: 600;
}

.repos__desc,
.repos__muted {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.repos__reload {
  flex-shrink: 0;
  margin-left: auto;
}

.repos__error {
  margin: 0;
  color: var(--color-error);
  font-size: var(--text-sm);
}

.repos__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.repos__table th {
  padding: 0 var(--space-3) var(--space-2) 0;
  text-align: left;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
}

.repos__table td {
  padding: var(--space-3) var(--space-3) var(--space-3) 0;
  vertical-align: top;
  border-bottom: 1px solid var(--color-border);
}

.row__name {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.row__path,
.row__branch {
  display: block;
  margin-top: 2px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  word-break: break-all;
}

.row__branch {
  color: var(--color-text-secondary);
}

.row__link {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.row__select {
  width: auto;
  min-width: 190px;
  padding: 6px 10px;
}

.row__slug,
.row__base {
  width: 170px;
  padding: 6px 10px;
}

.row__actions {
  white-space: nowrap;
  text-align: right;
}

.row__actions .btn + .btn {
  margin-left: var(--space-2);
}

.row__feedback {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-success-text);
}

.row__feedback[data-type='error'] {
  color: var(--color-error);
}

.pill {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-neutral-surface);
  color: var(--color-neutral-text);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.pill--success {
  background: var(--color-success-surface);
  color: var(--color-success-text);
}

.pill--warning {
  background: var(--color-warning-surface);
  color: var(--color-warning-text);
}

.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
