<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { CircleCheck, X } from 'lucide-vue-next'
import { useContextsStore } from '@/stores/contexts'

const store = useContextsStore()
const r = computed(() => store.resolver)
const issueInput = ref(null)
const resolutionInput = ref(null)

const KEY = /^[A-Z][A-Z0-9]{1,9}-\d{1,7}$/
const valid = computed(() => KEY.test(r.value.issue_key.trim().toUpperCase()))

watch(
  () => store.resolver.open,
  async (open) => {
    if (!open) return
    await nextTick()
    if (r.value.issue_key) resolutionInput.value?.focus()
    else issueInput.value?.focus()
  },
)

async function save() {
  if (valid.value && !r.value.saving) await store.saveResolver()
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    store.closeResolver()
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    save()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="r.open" class="resolve-backdrop" @mousedown.self="store.closeResolver()">
      <form class="resolve" role="dialog" aria-modal="true" aria-label="Resolver ponto em aberto" @submit.prevent="save" @keydown="onKeydown">
        <header class="resolve__header">
          <CircleCheck :size="18" />
          <h2>Resolver ponto em aberto</h2>
          <button type="button" class="resolve__icon" title="Fechar (Esc)" @click="store.closeResolver()"><X :size="16" /></button>
        </header>

        <blockquote class="resolve__point">
          <strong>{{ r.context.title || 'Sem título' }}</strong>
          <span>aberto em {{ r.context.issue.key }}</span>
        </blockquote>

        <div class="field">
          <label class="field__label" for="resolve-issue">Resolvido na tarefa</label>
          <input
            id="resolve-issue"
            ref="issueInput"
            v-model="r.issue_key"
            class="field__input"
            placeholder="WAI-1234"
            maxlength="20"
            @blur="r.issue_key = r.issue_key.toUpperCase()"
          >
        </div>
        <div class="field">
          <label class="field__label" for="resolve-text">Como foi resolvido</label>
          <textarea
            id="resolve-text"
            ref="resolutionInput"
            v-model="r.resolution"
            class="field__input resolve__text"
            rows="4"
            maxlength="5000"
            placeholder="Opcional — o que foi feito, PR, decisão tomada…"
          />
        </div>

        <footer class="resolve__footer">
          <p v-if="r.error" class="resolve__error" role="alert">{{ r.error }}</p>
          <button type="button" class="btn btn--secondary" @click="store.closeResolver()">Cancelar</button>
          <button type="submit" class="btn btn--primary" :disabled="!valid || r.saving">
            {{ r.saving ? 'Salvando…' : 'Marcar como resolvido' }}
          </button>
        </footer>
      </form>
    </div>
  </Teleport>
</template>

<style scoped>
.resolve-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: start center;
  padding: 14vh var(--space-4) var(--space-4);
  background: var(--color-overlay);
}

.resolve {
  width: min(520px, 100%);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5) var(--space-5);
  border: 1px solid var(--color-border);
  border-top: 5px solid var(--color-success);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-modal);
}

.resolve__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-success);
}

.resolve__header h2 {
  flex: 1;
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text);
}

.resolve__icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-muted);
}

.resolve__point {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-left: 3px solid var(--color-warning-text);
  border-radius: var(--radius-sm);
  background: var(--color-warning-surface);
  font-size: var(--text-sm);
}

.resolve__point span {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.resolve__text {
  resize: vertical;
}

.resolve__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
}

.resolve__error {
  flex-basis: 100%;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-surface);
  color: var(--color-error);
  font-size: var(--text-sm);
}
</style>
