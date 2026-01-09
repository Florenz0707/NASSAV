import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
    plugins: [vue()],
    server: {
        port: 9780,
        proxy: {
            '/nassav/api': {
                target: 'http://localhost:9790',
                changeOrigin: true
            }
        }
    },
    resolve: {
        alias: {
            '@': '/src'
        }
    }
})
