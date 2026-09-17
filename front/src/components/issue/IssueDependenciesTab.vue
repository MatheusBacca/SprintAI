<script setup>
import IssueRef from './IssueRef.vue'

defineProps({
  issue: { type: Object, required: true },
})
const emit = defineEmits(['open'])
</script>

<template>
  <div class="deps">
    <section v-if="issue.parent" class="deps__group">
      <h2 class="deps__title">Pai</h2>
      <ul class="deps__list"><IssueRef :item="issue.parent" @open="emit('open', $event)" /></ul>
    </section>

    <section v-if="issue.children.length" class="deps__group">
      <h2 class="deps__title">Filhas <span>{{ issue.children.length }}</span></h2>
      <ul class="deps__list">
        <IssueRef v-for="c in issue.children" :key="c.key" :item="c" @open="emit('open', $event)" />
      </ul>
    </section>

    <section v-for="group in issue.dependencies" :key="`${group.kind}:${group.label}`" class="deps__group" :data-kind="group.kind">
      <h2 class="deps__title">{{ group.label }} <span>{{ group.items.length }}</span></h2>
      <ul class="deps__list">
        <IssueRef v-for="item in group.items" :key="item.key" :item="item" @open="emit('open', $event)" />
      </ul>
    </section>

    <p v-if="!issue.parent && !issue.children.length && !issue.dependencies.length" class="deps__empty">
      Nenhuma dependência registrada no Jira.
    </p>
  </div>
</template>

<style scoped>
.deps {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.deps__title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-text-secondary);
}

.deps__title span {
  padding: 0 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted);
}

.deps__group[data-kind='blocked_by'] .deps__title {
  color: var(--color-error);
}

.deps__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.deps__empty {
  margin: 0;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
</style>
