<script setup>
import { onMounted, onUnmounted, watch, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import Navbar from './app/components/Navbar.vue'
import LoginView from './views/LoginView.vue'
import Toast from './shared/ui/Toast.vue'
import { useWebSocketStore } from './app/stores/websocket.js'
import { useSettingsStore } from './features/settings/stores/settings.js'
import { useResourceStore } from './features/resources/stores/resource.js'
import { useTaskJobsStore } from './features/tasks/stores/taskJobs.js'
import { useSessionStore } from './features/auth/stores/session.js'

const mainContent = ref(null)
const route = useRoute()
let focusAfterNavigation = false
watch(
  () => route.path,
  () => {
    focusAfterNavigation = true
  }
)
function restorePageFocus() {
  if (focusAfterNavigation) mainContent.value?.focus({ preventScroll: true })
  focusAfterNavigation = false
}
const taskJobs = useTaskJobsStore()
const wsStore = useWebSocketStore()
const settingsStore = useSettingsStore()
const resourceStore = useResourceStore()
const sessionStore = useSessionStore()

function refreshVisibleJobs() {
  if (sessionStore.status === 'authenticated' && document.visibilityState === 'visible') {
    resourceStore.refreshPendingScrapeJobs()
    taskJobs.poll(true)
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', refreshVisibleJobs)
  sessionStore.initialize()
})

watch(
  () => sessionStore.status,
  (status) => {
    if (status === 'authenticated') {
      taskJobs.start(sessionStore.username)
      wsStore.connect()
      settingsStore.loadSettings()
      resourceStore.restoreScrapeJobs()
    } else {
      wsStore.disconnect()
      resourceStore.stopScrapeTracking()
      taskJobs.reset()
    }
  }
)

onUnmounted(() => {
  document.removeEventListener('visibilitychange', refreshVisibleJobs)
  resourceStore.stopScrapeTracking()
  taskJobs.reset()
  wsStore.disconnect()
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
    <div
      v-if="sessionStore.status === 'checking'"
      class="flex min-h-screen items-center justify-center text-[var(--text-secondary)]"
      role="status"
    >
      正在检查登录状态…
    </div>
    <LoginView v-else-if="sessionStore.status !== 'authenticated'" />
    <template v-else>
      <a href="#main-content" class="skip-link">跳转到主要内容</a>
      <Navbar />
      <main id="main-content" ref="mainContent" tabindex="-1" class="main-content">
        <RouterView v-slot="{ Component }">
          <transition name="page" mode="out-in" @after-enter="restorePageFocus">
            <component :is="Component" />
          </transition>
        </RouterView>
      </main>
      <Toast />
    </template>
  </div>
</template>

<style scoped>
.skip-link {
  position: fixed;
  top: 0.5rem;
  left: 0.5rem;
  z-index: 100;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  background: var(--bg-secondary);
  color: var(--text-primary);
  transform: translateY(-200%);
}
.skip-link:focus {
  transform: translateY(0);
}
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
  background: var(--bg-primary);
  pointer-events: none;
  z-index: 0;
}

.main-content:focus {
  outline: none;
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
