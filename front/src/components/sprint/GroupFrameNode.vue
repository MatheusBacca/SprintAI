<script setup>
defineProps({
  data: { type: Object, required: true },
})
</script>

<template>
  <div class="frame" :style="{ width: `${data.width}px`, height: `${data.height}px` }">
    <span class="frame__label">
      <template v-if="data.title">{{ data.title }} · </template>{{ data.count }} tarefa(s) na sprint
    </span>
  </div>
</template>

<style scoped>
.frame {
  box-sizing: border-box;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-surface-muted) 55%, transparent);
  pointer-events: none;
}

.frame__label {
  display: inline-block;
  margin: 10px 14px;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
}
</style>
