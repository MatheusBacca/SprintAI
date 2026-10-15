<script setup>
import { comboKeys } from '@/utils/shortcuts'

/**
 * Dica de um controle do topo: o que ele faz e o atalho, ao passar o mouse (ou chegar pelo
 * Tab). O atalho mora aqui, e não no botão, para o topo não virar uma fileira de teclas —
 * ele só aparece para quem está olhando aquele controle.
 *
 * `lines`: `[{ label, combo }]`; atalho desativado em Configurações (`combo` nulo) deixa só
 * o rótulo. `detail`: texto de apoio embaixo, como o erro do último sync.
 */
defineProps({
  lines: { type: Array, required: true },
  detail: { type: String, default: null },
})
</script>

<template>
  <span class="tip">
    <slot />
    <span class="tip__bubble" role="tooltip">
      <span v-for="line in lines" :key="line.label" class="tip__line">
        <span class="tip__label">{{ line.label }}</span>
        <span v-if="line.combo" class="tip__keys">
          <kbd v-for="key in comboKeys(line.combo)" :key="key">{{ key }}</kbd>
        </span>
      </span>
      <span v-if="detail" class="tip__detail">{{ detail }}</span>
    </span>
  </span>
</template>

<style scoped>
.tip {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  min-width: 0;
}

/* Alinhada pela direita do controle: o topo termina ali, e a dica não sai da tela. */
.tip__bubble {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: var(--z-popover);
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
  font-size: var(--text-xs);
  color: var(--color-text);
  white-space: nowrap;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition:
    opacity var(--duration-fast),
    visibility var(--duration-fast);
}

/* Um respiro antes de abrir: passar o mouse pelo topo a caminho de outro lugar não pisca. */
.tip:hover > .tip__bubble,
.tip:has(:focus-visible) > .tip__bubble {
  opacity: 1;
  visibility: visible;
  transition-delay: 300ms;
}

/* Com um painel do topo aberto — deste controle ou do vizinho, aberto pelo atalho com o
   mouse parado noutro botão —, a dica cobriria o painel. O `:global` leva o seletor
   inteiro: com só o `.topbar` dentro dele, o Vue descarta o resto e a regra sumia com o
   topo todo. */
:global(.topbar:has([aria-expanded='true']) .tip__bubble) {
  display: none;
}

.tip__line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.tip__label {
  font-weight: 600;
}

.tip__keys {
  display: inline-flex;
  gap: 3px;
}

.tip__keys kbd {
  min-width: 20px;
  padding: 0 5px;
  border: 1px solid var(--color-border-strong);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--color-surface-muted);
  font-size: 11px;
  line-height: 16px;
  text-align: center;
  color: var(--color-text);
}

.tip__detail {
  max-width: 300px;
  color: var(--color-text-secondary);
  white-space: pre-line;
}
</style>
