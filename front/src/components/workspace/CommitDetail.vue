<script setup>
import { computed } from 'vue'
import { Copy, X } from 'lucide-vue-next'
import IssueKeyChip from './IssueKeyChip.vue'
import { copyRichText } from '@/utils/clipboard'
import { formatDateTime } from '@/utils/datetime'

/**
 * Detalhe do commit escolhido na linha do tempo: autor, mensagem e arquivos com +/-.
 * A mensagem é do git — texto puro, com quebra de linha, nunca HTML.
 */
const props = defineProps({
  sha: { type: String, required: true },
  detail: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  issueStatus: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close', 'select', 'open-issue'])

const totals = computed(() => {
  const files = props.detail?.files ?? []
  return {
    added: files.reduce((n, f) => n + (f.added ?? 0), 0),
    deleted: files.reduce((n, f) => n + (f.deleted ?? 0), 0),
  }
})
</script>

<template>
  <aside class="detail" aria-label="Detalhe do commit">
    <header class="detail__header">
      <code class="detail__sha">{{ sha.slice(0, 10) }}</code>
      <button type="button" class="detail__icon" title="Copiar o hash" aria-label="Copiar o hash" @click="copyRichText({ text: sha })">
        <Copy :size="13" />
      </button>
      <button type="button" class="detail__icon detail__close" title="Fechar" aria-label="Fechar" @click="emit('close')">
        <X :size="14" />
      </button>
    </header>

    <p v-if="error" class="detail__error" role="alert">{{ error }}</p>
    <p v-else-if="loading || !detail" class="detail__muted">Carregando…</p>
    <template v-else>
      <p class="detail__meta">
        <strong>{{ detail.author }}</strong> · {{ formatDateTime(detail.committed_at ?? detail.authored_at) }}
      </p>
      <p class="detail__message">{{ detail.message }}</p>

      <p v-if="detail.issue_keys.length" class="detail__keys">
        <IssueKeyChip
          v-for="key in detail.issue_keys"
          :key="key"
          class="detail__key"
          :issue-key="key"
          :status="issueStatus[key]"
          @open="emit('open-issue', $event)"
        />
      </p>

      <p v-if="detail.parents.length" class="detail__parents">
        {{ detail.parents.length > 1 ? 'Pais' : 'Pai' }}:
        <button v-for="parent in detail.parents" :key="parent" type="button" class="detail__parent" @click="emit('select', parent)">
          {{ parent.slice(0, 7) }}
        </button>
      </p>

      <h3 class="detail__files-title">
        {{ detail.files.length }} arquivo(s)
        <span class="detail__plus">+{{ totals.added }}</span>
        <span class="detail__minus">−{{ totals.deleted }}</span>
      </h3>
      <ul class="detail__files">
        <li v-for="file in detail.files" :key="file.path" :title="file.path">
          <span class="detail__path">{{ file.path }}</span>
          <span v-if="file.added == null" class="detail__muted">binário</span>
          <template v-else>
            <span class="detail__plus">+{{ file.added }}</span>
            <span class="detail__minus">−{{ file.deleted }}</span>
          </template>
        </li>
      </ul>
      <p v-if="detail.files_truncated" class="detail__muted">Mais arquivos no commit — a lista para em 300.</p>
    </template>
  </aside>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 340px;
  min-height: 0;
  padding: var(--space-3) var(--space-4);
  overflow: auto;
  border-left: 1px solid var(--color-border);
  background: var(--color-surface);
  font-size: var(--text-xs);
}

.detail__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.detail__sha {
  font-size: var(--text-sm);
  font-weight: 600;
}

.detail__icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text-muted);
}

.detail__icon:hover {
  color: var(--color-primary);
}

.detail__close {
  margin-left: auto;
}

.detail__meta,
.detail__parents,
.detail__keys,
.detail__muted,
.detail__error {
  margin: 0;
  color: var(--color-text-secondary);
}

.detail__error {
  color: var(--color-error);
}

.detail__message {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail__key {
  margin-right: 4px;
}

.detail__parent {
  margin-right: 4px;
  padding: 0 6px;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.detail__files-title {
  display: flex;
  gap: var(--space-2);
  margin: var(--space-2) 0 0;
  font-size: var(--text-xs);
  font-weight: 600;
}

.detail__files {
  margin: 0;
  padding: 0;
  list-style: none;
}

.detail__files li {
  display: flex;
  gap: var(--space-2);
  padding: 3px 0;
  border-bottom: 1px solid var(--color-border);
}

.detail__path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-mono);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail__plus {
  color: var(--color-success-text);
}

.detail__minus {
  color: var(--color-error);
}
</style>
