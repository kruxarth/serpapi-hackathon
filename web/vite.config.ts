import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server proxies /api to the local backend, so the browser only ever talks to 127.0.0.1.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: false } },
  },
  build: { chunkSizeWarningLimit: 1500 },
})
