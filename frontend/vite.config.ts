import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Dev-only proxy so the browser talks to one origin, like production behind Vercel.
  const apiTarget = env.TENQ_DEV_API_TARGET ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { '/api': { target: apiTarget, changeOrigin: false } },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      restoreMocks: true,
    },
  }
})
