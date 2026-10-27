/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Shared with scripts/wait-and-open.mjs, which opens the browser once the app answers.
import devServer from './dev-server.json' with { type: 'json' }

// The backend listens on 127.0.0.1:8000 (see backend/app/config.py).
// In development, Vite proxies /api so the browser only ever talks to one origin.
const backendUrl = process.env.VOCAB_BACKEND_URL ?? devServer.backendUrl

export default defineConfig({
  plugins: [react()],
  server: {
    host: devServer.host,
    port: devServer.port,
    strictPort: true,
    // Tests only: the unit limits test reads backend/app/domain/curriculum_unit.py (D-262).
    fs: process.env.VITEST ? { allow: ['..'] } : undefined,
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
