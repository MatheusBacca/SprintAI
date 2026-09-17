<script setup>
import { computed, ref } from 'vue'
import { CheckCircle2, CircleAlert, CircleDashed, ExternalLink } from 'lucide-vue-next'
import { formatRelative } from '@/utils/time'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  status: { type: Object, default: () => ({ configured: false }) },
  busy: { type: String, default: null },
  feedback: { type: Object, default: null },
  helpUrl: { type: String, default: '' },
  helpLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['submit', 'test', 'remove'])

const confirmingRemoval = ref(false)

const state = computed(() => {
  if (props.disabled) return 'disabled'
  if (!props.status.configured) return 'empty'
  return props.status.last_error ? 'error' : 'ok'
})

const stateLabel = computed(
  () =>
    ({
      disabled: 'Em breve',
      empty: 'Não configurado',
      error: 'Com erro',
      ok: 'Conectado',
    })[state.value],
)

const validatedLabel = computed(() => formatRelative(props.status.validated_at))
const checkedLabel = computed(() => formatRelative(props.status.last_checked_at))

function onRemove() {
  if (!confirmingRemoval.value) {
    confirmingRemoval.value = true
    return
  }
  confirmingRemoval.value = false
  emit('remove')
}
</script>

<template>
  <article class="conn card" :class="`conn--${state}`">
    <header class="conn__header">
      <div>
        <h2 class="conn__title">{{ title }}</h2>
        <p v-if="description" class="conn__description">{{ description }}</p>
      </div>
      <span class="conn__chip" :data-state="state">
        <CheckCircle2 v-if="state === 'ok'" :size="14" />
        <CircleAlert v-else-if="state === 'error'" :size="14" />
        <CircleDashed v-else :size="14" />
        {{ stateLabel }}
      </span>
    </header>

    <dl v-if="status.configured" class="conn__meta">
      <dt>Conta</dt>
      <dd>{{ status.account_name ?? '—' }}</dd>
      <dt>Validado</dt>
      <dd>{{ validatedLabel ?? '—' }}</dd>
      <template v-if="status.last_error">
        <dt>Último teste</dt>
        <dd class="conn__error-text">{{ checkedLabel }} · {{ status.last_error }}</dd>
      </template>
    </dl>

    <form class="conn__form" :aria-disabled="disabled" @submit.prevent="emit('submit')">
      <fieldset :disabled="disabled || !!busy">
        <slot />
      </fieldset>

      <p v-if="feedback" class="conn__feedback" :data-type="feedback.type" role="status">
        {{ feedback.text }}
      </p>

      <footer v-if="!disabled" class="conn__actions">
        <a v-if="helpUrl" :href="helpUrl" target="_blank" rel="noopener noreferrer" class="conn__help">
          {{ helpLabel }} <ExternalLink :size="12" />
        </a>
        <button
          v-if="status.configured"
          type="button"
          class="btn btn--ghost-danger"
          :disabled="!!busy"
          @click="onRemove"
          @blur="confirmingRemoval = false"
        >
          {{ busy === 'removing' ? 'Removendo…' : confirmingRemoval ? 'Confirmar remoção' : 'Remover' }}
        </button>
        <button
          v-if="status.configured"
          type="button"
          class="btn btn--secondary"
          :disabled="!!busy"
          @click="emit('test')"
        >
          {{ busy === 'testing' ? 'Testando…' : 'Testar conexão' }}
        </button>
        <button type="submit" class="btn btn--primary" :disabled="!!busy">
          {{ busy === 'saving' ? 'Testando e salvando…' : 'Salvar e testar' }}
        </button>
      </footer>
    </form>
  </article>
</template>

<style scoped>
.conn {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.conn--disabled {
  opacity: 0.7;
}

.conn__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}

.conn__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}

.conn__description {
  margin: var(--space-1) 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.conn__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--color-surface-muted);
  color: var(--color-text-secondary);
}

.conn__chip[data-state='ok'] {
  background: var(--color-success-surface-soft);
  color: var(--color-success);
}

.conn__chip[data-state='error'] {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.conn__meta {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: var(--space-1) var(--space-3);
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-surface-muted);
  font-size: var(--text-sm);
}

.conn__meta dt {
  color: var(--color-text-secondary);
}

.conn__meta dd {
  margin: 0;
}

.conn__error-text {
  color: var(--color-error);
}

.conn__form fieldset {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.conn__feedback {
  margin: var(--space-3) 0 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.conn__feedback[data-type='success'] {
  background: var(--color-success-surface-soft);
  color: var(--color-success);
}

.conn__feedback[data-type='error'] {
  background: var(--color-error-surface);
  color: var(--color-error);
}

.conn__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.conn__help {
  margin-right: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-primary);
}
</style>
