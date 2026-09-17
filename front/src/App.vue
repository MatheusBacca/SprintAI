<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import AppShell from '@/layouts/AppShell.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

// Sem escolha manual, o tema acompanha o Windows enquanto o app está aberto.
let unwatchTheme = () => {}
onMounted(() => {
  unwatchTheme = ui.watchSystemTheme()
})
onBeforeUnmount(() => unwatchTheme())
</script>

<template>
  <AppShell>
    <RouterView />
  </AppShell>
</template>
