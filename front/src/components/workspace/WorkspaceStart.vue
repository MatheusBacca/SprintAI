<script setup>
import { computed, ref } from 'vue'
import { FolderGit2, Trash2 } from 'lucide-vue-next'
import { formatRelative } from '@/utils/time'

/**
 * Começo do Workspace: abrir pela chave da tarefa, criar um livre (só repositórios) ou
 * voltar a um que foi fechado. Pelo painel de qualquer tarefa também dá — o botão de
 * pasta no cabeçalho.
 */
const props = defineProps({
  closed: { type: Array, default: () => [] },
  repos: { type: Array, default: () => [] },
  opening: { type: Boolean, default: false },
  error: { type: String, default: null },
})
const emit = defineEmits(['open-issue', 'open-free', 'reopen', 'remove'])

const KEY = /^[A-Za-z][A-Za-z0-9]{1,9}-\d{1,7}$/

const issueKey = ref('')
const freeTitle = ref('')
const freeRepos = ref([])

const keyValid = computed(() => KEY.test(issueKey.value.trim()))
const freeValid = computed(() => freeTitle.value.trim().length > 0)

function openIssue() {
  if (keyValid.value) emit('open-issue', issueKey.value.trim().toUpperCase())
}

function openFree() {
  if (freeValid.value) emit('open-free', freeTitle.value.trim(), [...freeRepos.value])
}

const sortedRepos = computed(() => [...props.repos].sort((a, b) => a.slug.localeCompare(b.slug)))
</script>

<template>
  <section class="start">
    <header class="start__header">
      <FolderGit2 :size="22" />
      <div>
        <h1 class="start__title">Workspace</h1>
        <p class="start__desc">
          Os cards de uma feature, a linha do tempo das branches de cada repositório envolvido e um
          terminal na pasta de cada um — tudo numa aba.
        </p>
      </div>
    </header>

    <p v-if="error" class="start__error" role="alert">{{ error }}</p>

    <div class="start__grid">
      <form class="start__card card" @submit.prevent="openIssue">
        <h2>Pela tarefa</h2>
        <p class="field__hint">
          Épico, Enhancements ou Feature traz as filhas; uma Tarefa traz as subtarefas e as vizinhas por
          bloqueio, origem e Relates.
        </p>
        <div class="start__row">
          <input v-model="issueKey" class="field__input" placeholder="WAI-8677" aria-label="Chave da tarefa" autocomplete="off">
          <button type="submit" class="btn btn--primary" :disabled="!keyValid || opening">Abrir</button>
        </div>
      </form>

      <form class="start__card card" @submit.prevent="openFree">
        <h2>Livre</h2>
        <p class="field__hint">Sem tarefa: só os repositórios que você escolher, para ter terminal à mão.</p>
        <input v-model="freeTitle" class="field__input" placeholder="Nome do workspace" aria-label="Nome do workspace" maxlength="120">
        <div class="start__repos" role="group" aria-label="Repositórios">
          <label v-for="repo in sortedRepos" :key="repo.slug" class="start__repo">
            <input v-model="freeRepos" type="checkbox" :value="repo.slug">
            {{ repo.slug }}
          </label>
        </div>
        <button type="submit" class="btn btn--secondary start__submit" :disabled="!freeValid || opening">Criar workspace livre</button>
      </form>
    </div>

    <section v-if="closed.length" class="start__closed">
      <h2>Abertos antes</h2>
      <ul>
        <li v-for="ws in closed" :key="ws.id" :data-id="ws.id">
          <button type="button" class="start__reopen" @click="emit('reopen', ws.id)">
            <strong v-if="ws.root_issue_key">{{ ws.root_issue_key }}</strong>
            <span>{{ ws.title }}</span>
            <span class="muted">{{ formatRelative(ws.last_opened_at) }}</span>
          </button>
          <button type="button" class="start__remove" title="Apagar workspace" aria-label="Apagar workspace" @click="emit('remove', ws.id)">
            <Trash2 :size="14" />
          </button>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.start {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--space-5) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.start__header {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

.start__header > svg {
  flex-shrink: 0;
  margin-top: 4px;
  color: var(--color-primary);
}

.start__title {
  margin: 0 0 4px;
  font-size: var(--text-xl);
}

.start__desc {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.start__error {
  margin: 0;
  color: var(--color-error);
  font-size: var(--text-sm);
}

.start__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--space-4);
}

.start__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-5);
}

.start__card h2,
.start__closed h2 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.start__row {
  display: flex;
  gap: var(--space-2);
}

.start__repos {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  max-height: 140px;
  overflow: auto;
  font-size: var(--text-sm);
}

.start__repo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.start__submit {
  align-self: flex-start;
}

.start__closed ul {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
}

.start__closed li {
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.start__reopen {
  flex: 1;
  min-width: 0;
  display: flex;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 0;
  background: none;
  text-align: left;
  font-size: var(--text-sm);
  color: inherit;
}

.start__reopen strong {
  color: var(--color-primary);
}

.start__reopen span:nth-of-type(1) {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.start__remove {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 0;
  background: none;
  color: var(--color-text-muted);
}

.start__remove:hover {
  color: var(--color-error);
}
</style>
