/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend listens on 127.0.0.1:8000 (see backend/app/config.py).
// In development, Vite proxies /api so the browser only ever talks to one origin.
const backendUrl = process.env.VOCAB_BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // start.ps1 / start.sh set this so the browser opens once the dev server is ready.
    open: process.env.VOCAB_OPEN_BROWSER === '1',
    proxy: {
      '/api': { target: backendUrl, changeOrigin: true },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
