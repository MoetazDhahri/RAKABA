import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Same pattern as frontend/admin/vite.config.js: dev proxies to the FastAPI
// backend so relative fetch('/api/...') calls work identically in
// `npm run dev` and in the built app served by FastAPI at /espace-client.
export default defineConfig({
  plugins: [react()],
  base: '/espace-client/',
  server: {
    port: 5175,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
