import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // The jury build is a static site: relative asset paths let it run from any host or subfolder.
  base: mode === 'jury' ? './' : '/',
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
  build: { outDir: mode === 'jury' ? 'dist-jury' : 'dist' },
}))
