import { defineConfig } from 'vitest/config'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8686',
      '/tiles': 'http://127.0.0.1:8686',
      '/ws': { target: 'ws://127.0.0.1:8686', ws: true },
    },
  },
  build: { outDir: 'dist' },
  test: { environment: 'node' },
})
