import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 9780,
    proxy: {
      '/nassav/api': {
        target: 'http://localhost:9790',
        changeOrigin: false,
      },
      '/nassav/ws': {
        target: 'ws://localhost:9790',
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
