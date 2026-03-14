<script setup>
import { onMounted, watch } from 'vue'
import { RouterView } from 'vue-router'
import Navbar from './components/Navbar.vue'
import Toast from './components/Toast.vue'
import { useWebSocketStore } from './stores/websocket'
import { useSettingsStore } from './stores/settings'

const wsStore = useWebSocketStore()
const settingsStore = useSettingsStore()

// 应用启动时立即连接 WebSocket 并加载用户设置
onMounted(() => {
  wsStore.connect()
  settingsStore.loadSettings()
})

// 监听字体设置变化，应用到 body（仅在保存后触发）
watch(
  () => settingsStore.fontFamily,
  (newFont) => {
    if (newFont) {
      // 添加字体回退链，使用系统字体作为兜底方案
      document.body.style.fontFamily = `'${newFont}', 'Mplus2', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', Roboto, 'Noto Sans CJK', sans-serif`
    }
  }
)

// 监听主题模式变化，应用到 body
watch(
  () => settingsStore.colorMode,
  (newMode) => {
    if (newMode === 'light') {
      document.body.classList.remove('dark-mode')
      document.body.classList.add('light-mode')
    } else {
      document.body.classList.remove('light-mode')
      document.body.classList.add('dark-mode')
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="app">
    <div class="background-pattern" />
    <Navbar />
    <main class="main-content">
      <RouterView v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>
    <Toast />
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  position: relative;
}

.background-pattern {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background:
    radial-gradient(ellipse at 20% 20%, rgba(120, 119, 198, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 80%, rgba(255, 119, 115, 0.1) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, rgba(78, 205, 196, 0.08) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

.main-content {
  position: relative;
  z-index: 1;
  padding: 2rem;
  padding-top: calc(4rem + 2rem);
  max-width: 1400px;
  margin: 0 auto;
}

@media (max-width: 640px) {
  .main-content {
    padding: 1rem;
    padding-top: calc(4rem + 1rem);
  }
}

.page-enter-active,
.page-leave-active {
  transition: all 0.3s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}
</style>
