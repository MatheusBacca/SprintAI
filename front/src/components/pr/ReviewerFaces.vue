<script setup>
import { computed } from 'vue'
import ReviewerAvatar from './ReviewerAvatar.vue'
import { REVIEW_PERSON_LABEL } from '@/constants/prStatus'

/**
 * As fotos de quem revisa, dentro do badge de PR — no lugar da barra da review. Cada uma
 * pintada com o estado da pessoa (aprovou, pediu ajuste, falta revisar), na ordem que o back
 * manda: a mesma da barra, então a leitura da esquerda para a direita continua sendo o
 * andamento.
 *
 * Só a foto: o badge mora no rodapé do card, e com três revisores o nome não cabe ao lado do
 * selo e do "Concluir". O nome e o estado vão no `title` de cada uma e no do badge. Nada aqui
 * é clicável — o badge em volta é o link do PR.
 */
const props = defineProps({
  people: { type: Array, required: true },
  /** Diâmetro do círculo pintado; a foto fica dentro dele, com a margem na cor do estado. */
  size: { type: Number, default: 17 },
})

// A foto não encosta na borda do círculo: sobra a margem pintada, que é o que diz o estado.
const RIM = 2
const photo = computed(() => props.size - 2 * RIM)
const circle = computed(() => ({ '--face-size': `${props.size}px`, '--face-rim': `${RIM}px` }))
</script>

<template>
  <span class="faces" :style="circle" aria-hidden="true">
    <span
      v-for="(person, index) in people"
      :key="person.account_id ?? `${person.name}-${index}`"
      class="faces__face"
      :data-state="person.state"
      :title="`${person.name ?? 'Revisor'} — ${REVIEW_PERSON_LABEL[person.state] ?? person.state}`"
    >
      <ReviewerAvatar :name="person.name" :url="person.avatar_url" :size="photo" />
    </span>
  </span>
</template>

<style scoped>
.faces {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 1px;
}

/* O círculo inteiro pintado na cor do estado — as cores que a barra usava —, com a foto
   menor no meio: a margem colorida em volta dela é o que se lê de longe. */
.faces__face {
  --face: var(--color-border-strong);

  box-sizing: border-box;
  display: inline-grid;
  place-items: center;
  width: var(--face-size);
  height: var(--face-size);
  padding: var(--face-rim);
  border-radius: 50%;
  background: color-mix(in srgb, var(--face) 55%, var(--color-surface));
  box-shadow: 0 0 0 1px var(--face);
  --avatar-fill: color-mix(in srgb, var(--face) 22%, var(--color-surface));
  --avatar-ink: color-mix(in srgb, var(--face) 55%, var(--color-text));
}

.faces__face[data-state='approved'] {
  --face: var(--pr-approved);
}

.faces__face[data-state='changes_requested'] {
  --face: var(--pr-changes);
}
</style>
