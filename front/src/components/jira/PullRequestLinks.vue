<script setup>
import { ExternalLink } from 'lucide-vue-next'
import PrStatusBadge from '@/components/pr/PrStatusBadge.vue'
import { useJiraActionsStore } from '@/stores/jiraActions'
import { safeUrl } from '@/utils/safeUrl'

/** Tarefa com mais de um PR: o badge abre esta lista para escolher qual ver no Bitbucket. */
defineProps({
  links: { type: Array, required: true },
  issueKey: { type: String, default: null },
})

const store = useJiraActionsStore()
</script>

<template>
  <div class="prlinks">
    <strong class="prlinks__title">{{ links.length }} PRs<template v-if="issueKey"> de {{ issueKey }}</template></strong>
    <ul class="prlinks__list">
      <li v-for="link in links" :key="`${link.repo_slug}#${link.id}`">
        <a
          v-if="safeUrl(link.url)"
          class="prlinks__item"
          :href="safeUrl(link.url)"
          target="_blank"
          rel="noopener noreferrer"
          :title="`Abrir ${link.repo_slug} #${link.id} no Bitbucket`"
          @click="store.close()"
        >
          <PrStatusBadge :status="link.status" size="sm" />
          <span class="prlinks__ref">{{ link.repo_slug }} #{{ link.id }}</span>
          <span class="prlinks__name">{{ link.title }}</span>
          <ExternalLink :size="12" class="prlinks__icon" aria-hidden="true" />
        </a>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.prlinks {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 340px;
  max-width: calc(100vw - 32px);
}

.prlinks__title {
  font-size: var(--text-sm);
}

.prlinks__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.prlinks__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text);
}

.prlinks__item:hover {
  background: var(--color-surface-hover);
}

.prlinks__ref {
  flex-shrink: 0;
  font-weight: 600;
  white-space: nowrap;
}

.prlinks__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
}

.prlinks__icon {
  flex-shrink: 0;
  color: var(--color-text-muted);
}
</style>
