<script setup>
import { resourceApi } from './api/resources.js'
import { computed, onMounted, onUnmounted, watch, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { clearPlaybackDrafts } from './features/playback/lib/progressDrafts.js'
import { useRecommendationsStore } from './features/recommendations/stores/recommendations.js'
import { clearAllRecommendationViewStates } from './features/recommendations/stores/recommendationViewState.js'
import { useViewingStore } from './features/viewing/stores/viewing.js'
import Navbar from './app/components/Navbar.vue'
import LoginView from './views/LoginView.vue'
import Toast from './shared/ui/Toast.vue'
import { useToastStore } from './shared/stores/toast.js'
import { useWebSocketStore } from './app/stores/websocket.js'
import { useSettingsStore } from './features/settings/stores/settings.js'
import { useResourceStore } from './features/resources/stores/resource.js'
import { useActorGroupsStore } from './features/catalog/stores/actorGroups.js'
import { useGenreGroupsStore } from './features/catalog/stores/genreGroups.js'
import { useDownloadQueueStore } from './features/resources/stores/downloadQueue.js'
import { useTaskJobsStore } from './features/tasks/stores/taskJobs.js'
import { useUserOperationsStore } from './features/tasks/stores/userOperations.js'
import LibraryOperationDialog from './features/library/components/LibraryOperationDialog.vue'
import { useLibraryCommandsStore } from './features/library/stores/commands.js'
import { useMembershipsStore } from './features/library/stores/memberships.js'
import { useSessionStore } from './features/auth/stores/session.js'

const mainContent = ref(null)
const route = useRoute()
const playbackLayout = computed(() => route.meta.layout === 'playback')
let focusAfterNavigation = false
watch(
  () => route.path,
  () => {
    focusAfterNavigation = true
  }
)
function restorePageFocus() {
  // A page transition may finish after a user has already opened a dialog.
  if (focusAfterNavigation && !document.querySelector('[role="dialog"][aria-modal="true"]'))
    mainContent.value?.focus({ preventScroll: true })
  focusAfterNavigation = false
}
const taskJobs = useTaskJobsStore()
const wsStore = useWebSocketStore()
const settingsStore = useSettingsStore()
const resourceStore = useResourceStore()
const sessionStore = useSessionStore()
watch(
  () => [sessionStore.identity, useMembershipsStore().revision],
  () => {
    resourceApi.resetCoverCache()
    resourceApi.invalidateMetadataCache()
    useActorGroupsStore().invalidate()
    useGenreGroupsStore().invalidate()
  },
  { flush: 'sync', immediate: true }
)
const sourceRoute = computed(() =>
  ['Recommendations', 'ActorResources', 'GenreResources'].includes(route.name)
)
const pageIdentity = computed(() =>
  sourceRoute.value
    ? `${sessionStore.identity}:${sessionStore.sourceIdentity}`
    : sessionStore.identity
)
watch(
  () => sessionStore.sourceIdentity,
  (next, previous) => {
    if (previous && next !== previous) {
      useRecommendationsStore().reset()
      resourceStore.invalidateSourceRequests()
    }
  }
)

async function refreshVisibleJobs() {
  if (sessionStore.status === 'authenticated' && document.visibilityState === 'visible') {
    if (!(await sessionStore.recheck())) return
    if (sessionStore.capabilities.shared_library) useMembershipsStore().invalidate()
    if (sessionStore.capabilities.shared_library) {
      useUserOperationsStore().poll(true)
      useUserOperationsStore().load()
    } else {
      resourceStore.refreshPendingScrapeJobs()
      taskJobs.poll(true)
    }
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', refreshVisibleJobs)
  sessionStore.initialize()
})

watch(
  () => [sessionStore.status, sessionStore.identity],
  ([status, identity], previous) => {
    wsStore.disconnect()
    useUserOperationsStore().reset()
    useLibraryCommandsStore().reset(
      status === 'authenticated' && sessionStore.capabilities.shared_library ? identity : ''
    )
    useMembershipsStore().reset(
      status === 'authenticated' && sessionStore.capabilities.shared_library
        ? sessionStore.identity
        : ''
    )
    useToastStore().clear()
    resourceStore.beginSession(status === 'authenticated' ? sessionStore.identity : '')
    useDownloadQueueStore().beginSession(status === 'authenticated' ? sessionStore.identity : '')
    useActorGroupsStore().reset()
    useGenreGroupsStore().reset()
    if (status === 'anonymous' || (previous?.[1] && previous[1] !== identity)) clearPlaybackDrafts()
    useViewingStore().reset()
    useRecommendationsStore().reset()
    settingsStore.reset()
    if (status === 'anonymous') {
      clearAllRecommendationViewStates()
    }
    if (status === 'authenticated') {
      if (sessionStore.capabilities.shared_library) {
        taskJobs.reset()
        useUserOperationsStore().start(sessionStore.identity)
      } else taskJobs.start(sessionStore.identity)
      wsStore.connect()
      settingsStore.loadSettings()
      if (!sessionStore.capabilities.shared_library) resourceStore.restoreScrapeJobs()
    } else {
      taskJobs.reset()
    }
  }
)

onUnmounted(() => {
  resourceApi.resetCoverCache()
  document.removeEventListener('visibilitychange', refreshVisibleJobs)
  resourceStore.stopScrapeTracking()
  taskJobs.reset()
  useUserOperationsStore().reset()
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
    <div class="background-pattern" aria-hidden="true">
      <div class="absolute inset-0 pointer-events-none opacity-60 overflow-hidden">
        <div
          class="absolute w-[500px] h-[500px] rounded-full opacity-40 blur-[80px] top-[-10%] right-[-5%]"
          style="background: var(--ambient-coral)"
        />
        <div
          class="absolute w-[400px] h-[400px] rounded-full opacity-40 blur-[80px] top-[40%] right-[-10%]"
          style="background: var(--accent-secondary)"
        />
        <div
          class="absolute w-[600px] h-[600px] rounded-full opacity-40 blur-[80px] bottom-[-10%] right-[-5%]"
          style="background: var(--accent-tertiary)"
        />
      </div>
    </div>
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
      <Navbar :logo-only="playbackLayout" />
      <main
        id="main-content"
        ref="mainContent"
        tabindex="-1"
        class="main-content"
        :class="{ 'main-content--playback': playbackLayout }"
      >
        <RouterView v-slot="{ Component }">
          <transition name="page" mode="out-in" @after-enter="restorePageFocus">
            <component :is="Component" :key="pageIdentity" />
          </transition>
        </RouterView>
      </main>
      <LibraryOperationDialog v-if="sessionStore.capabilities.shared_library" />
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
  background:
    radial-gradient(
      ellipse at 20% 20%,
      color-mix(in srgb, var(--accent-purple) 15%, transparent) 0%,
      transparent 50%
    ),
    radial-gradient(
      ellipse at 80% 80%,
      color-mix(in srgb, var(--ambient-coral) 10%, transparent) 0%,
      transparent 50%
    ),
    radial-gradient(
      ellipse at 50% 50%,
      color-mix(in srgb, var(--accent-tertiary) 8%, transparent) 0%,
      transparent 70%
    );
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

.main-content--playback {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
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
