<script setup>
defineProps({
  data: { type: Object, required: true },
})
</script>

<template>
  <div class="wave" :style="{ width: `${data.width}px` }">
    <span class="wave__label">{{ data.label }}</span>
    <span class="wave__line" />
  </div>
</template>

<style scoped>
.wave {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  box-sizing: border-box;
  pointer-events: none;
}

.wave__label {
  flex: none;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.wave__line {
  flex: 1;
  /* Tom próprio, um passo acima do pontilhado do fundo: com `--color-border-strong`
     a linha sumia contra a moldura do grupo no tema escuro. */
  border-top: 1px dashed var(--color-canvas-wave);
}
</style>
