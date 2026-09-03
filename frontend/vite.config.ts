import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': process.env.VITE_PROXY_TARGET || env.VITE_PROXY_TARGET || 'http://localhost:8000',
      },
    },
  }
})
