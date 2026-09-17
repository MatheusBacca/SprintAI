import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const apiTarget = `http://${env.API_HOST || '127.0.0.1'}:${env.API_PORT || '8765'}`

  // A porta sai do FRONT_ORIGIN do .env da raiz: é a mesma origem que a guarda
  // local do back libera. Duas fontes da verdade dariam um 403 no primeiro
  // request, e não um erro de porta ocupada.
  const frontOrigin = env.FRONT_ORIGIN || 'http://localhost:5273'
  const frontPort = Number(new URL(frontOrigin).port || 5273)

  return {
    plugins: [vue()],
    envDir: '..',
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: frontPort,
      // Sem strictPort o Vite cairia para a porta seguinte e o back recusaria a
      // origem com 403 — melhor falhar dizendo que a porta está ocupada.
      strictPort: true,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: false },
      },
    },
    test: {
      environment: 'jsdom',
      include: ['tests/**/*.spec.js'],
    },
  }
})
