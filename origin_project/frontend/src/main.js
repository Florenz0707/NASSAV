import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)
app.mount('#app')

// 全局错误处理
app.config.errorHandler = (err) => {
    console.error('Global error:', err)
}
