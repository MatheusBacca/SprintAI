<script setup>
import { computed, ref, watch } from 'vue'
import { safeUrl } from '@/utils/safeUrl'

/**
 * Foto do revisor no Bitbucket. Sem foto (PR espelhado antes dela) ou com a imagem que não
 * carregou, ficam as iniciais. Só https vira `src`, e sem referrer: o endereço do SprintAI
 * não vai junto para quem hospeda a foto.
 */
const props = defineProps({
  name: { type: String, default: null },
  url: { type: String, default: null },
  size: { type: Number, default: 18 },
})

const broken = ref(false)
watch(
  () => props.url,
  () => (broken.value = false),
)

const photo = computed(() => {
  const url = safeUrl(props.url)
  return !broken.value && url?.startsWith('https://') ? url : null
})

const initials = computed(() =>
  (props.name ?? '?')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase(),
)

const style = computed(() => ({ '--avatar-size': `${props.size}px` }))
</script>

<template>
  <img
    v-if="photo"
    class="avatar"
    :src="photo"
    :style="style"
    alt=""
    referrerpolicy="no-referrer"
    loading="lazy"
    @error="broken = true"
  >
  <span v-else class="avatar avatar--initials" :style="style" aria-hidden="true">{{ initials }}</span>
</template>

<style scoped>
.avatar {
  box-sizing: border-box;
  flex-shrink: 0;
  width: var(--avatar-size);
  height: var(--avatar-size);
  border-radius: 50%;
  object-fit: cover;
}

.avatar--initials {
  display: inline-grid;
  place-items: center;
  background: var(--avatar-fill, var(--color-surface-muted));
  font-size: calc(var(--avatar-size) * 0.42);
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.02em;
  color: var(--avatar-ink, var(--color-text-secondary));
}
</style>
