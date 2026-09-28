import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backend = new URL(process.env.NASSAV_VITE_BACKEND_URL || 'http://127.0.0.1:9790')
if (
  !['http:', 'https:'].includes(backend.protocol) ||
  backend.pathname !== '/' ||
  backend.search ||
  backend.hash ||
  backend.username ||
  backend.password
) {
  throw new Error('NASSAV_VITE_BACKEND_URL must be an HTTP(S) origin')
}
const websocketBackend = new URL(backend)
websocketBackend.protocol = backend.protocol === 'https:' ? 'wss:' : 'ws:'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: process.env.NASSAV_VITE_HOST || '127.0.0.1',
    port: 9780,
    proxy: {
      '/nassav/api': {
        target: backend.origin,
        changeOrigin: false,
      },
      '/nassav/ws': {
        target: websocketBackend.origin,
        ws: true,
        changeOrigin: false,
      },
    },
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
})
