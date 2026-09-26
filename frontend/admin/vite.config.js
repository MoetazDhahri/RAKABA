import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies API calls to the FastAPI backend (uvicorn main:app,
// run from the repo root) so relative fetch('/pipeline1/...') calls work
// identically in `npm run dev` and in the built app served by FastAPI at
// /admin (where there's no cross-origin boundary at all).
export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  server: {
    proxy: {
      '/pipeline1': 'http://localhost:8000',
      '/pipeline2': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
    },
  },
})
