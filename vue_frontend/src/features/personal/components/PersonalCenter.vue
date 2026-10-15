<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ConfirmDialog from '../../../shared/ui/ConfirmDialog.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
import ViewingLibrary from '../../viewing/components/ViewingLibrary.vue'
import PersonalSettings from '../../settings/components/PersonalSettings.vue'
import { useSessionStore } from '../../auth/stores/session.js'
const route = useRoute(),
  router = useRouter(),
  session = useSessionStore()
const sections = [
  { value: 'watch-later', label: '稍后再看' },
  { value: 'history', label: '观看历史' },
  { value: 'general', label: '通用设置' },
  { value: 'playback', label: '播放设置' },
]
const current = computed(() =>
  sections.some((s) => s.value === route.params.section) ? route.params.section : 'watch-later'
)
const confirmLogout = ref(false)
const error = ref(''),
  exiting = ref(false)
async function logout() {
  if (exiting.value) return
  confirmLogout.value = false
  exiting.value = true
  error.value = ''
  try {
    await session.signOut()
  } catch {
    error.value = '退出失败，请重试'
  } finally {
    exiting.value = false
  }
}
</script>
<template>
  <section class="max-w-7xl mx-auto px-4 py-8" aria-labelledby="personal-center-title">
    <header class="mb-8">
      <h1 id="personal-center-title" class="text-2xl font-semibold text-primary">个人中心</h1>
      <p class="text-muted text-sm mt-2">管理当前账号的观看列表与个人偏好</p>
    </header>
    <div class="grid grid-cols-1 lg:grid-cols-[12rem_minmax(0,1fr)] gap-8 items-start">
      <nav aria-label="个人中心功能" class="flex flex-wrap lg:flex-col gap-2 self-start lg:w-48">
        <AppButton
          v-for="section in sections"
          :key="section.value"
          class="lg:w-full whitespace-nowrap"
          :variant="current === section.value ? 'primary' : 'neutral'"
          :aria-current="current === section.value ? 'page' : undefined"
          @click="router.push({ name: 'PersonalCenter', params: { section: section.value } })"
          >{{ section.label }}</AppButton
        >
        <AppButton
          v-if="session.capabilities.app_admin"
          variant="neutral"
          class="lg:w-full whitespace-nowrap"
          @click="router.push({ name: 'Management', params: { section: 'accounts' } })"
          >管理中心</AppButton
        >
        <AppButton
          variant="neutral"
          class="lg:w-full whitespace-nowrap"
          :loading="exiting"
          loading-text="正在退出"
          @click="confirmLogout = true"
          >退出登录</AppButton
        >
        <p v-if="error" role="alert" class="text-accent-danger text-sm">{{ error }}</p>
      </nav>
      <div class="min-w-0">
        <Transition name="personal-section" mode="out-in">
          <KeepAlive :max="4">
            <component
              :is="['history', 'watch-later'].includes(current) ? ViewingLibrary : PersonalSettings"
              :key="
                ['history', 'watch-later'].includes(current)
                  ? `viewing:${current}`
                  : `settings:${current}`
              "
              v-bind="
                ['history', 'watch-later'].includes(current)
                  ? { initialKind: current }
                  : { section: current }
              "
              embedded
            />
          </KeepAlive>
        </Transition>
      </div>
    </div>
    <ConfirmDialog
      :show="confirmLogout"
      title="退出登录"
      message="是否要登出"
      confirm-text="登出"
      @confirm="logout"
      @cancel="confirmLogout = false"
    />
  </section>
</template>

<style scoped>
.personal-section-enter-active,
.personal-section-leave-active {
  transition:
    opacity 180ms ease,
    transform 180ms ease;
}
.personal-section-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.personal-section-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .personal-section-enter-active,
  .personal-section-leave-active {
    transition: none;
  }
}
</style>
