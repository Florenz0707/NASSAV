<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { playbackApi } from '../../../api/playback.js'
import { resourceApi } from '../../../api/resources.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import RequestError from '../../../shared/ui/RequestError.vue'
import EmptyState from '../../../shared/ui/EmptyState.vue'
import ResourceCover from '../../../shared/ui/ResourceCover.vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { useRouter } from 'vue-router'
const settings = useSettingsStore(),
  router = useRouter()
const items = ref([]),
  loading = ref(false),
  error = ref(''),
  disabled = ref(false)
const guard = createRequestGuard()
async function load() {
  if (disabled.value || loading.value) return
  const ticket = guard.begin()
  loading.value = true
  error.value = ''
  try {
    const response = await playbackApi.continuations()
    if (guard.current(ticket)) items.value = response.data || []
  } catch (failure) {
    if (guard.current(ticket)) {
      if (failure.httpStatus === 404) disabled.value = true
      else error.value = failure.message || '读取继续观看记录失败'
    }
  } finally {
    if (guard.current(ticket)) loading.value = false
  }
}
function refreshVisible() {
  if (document.visibilityState === 'visible') void load()
}
function time(value) {
  const seconds = Math.floor(value)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
function open(item) {
  window.open(
    router.resolve({ name: 'Playback', params: { avid: item.avid }, query: { mode: item.mode } })
      .href,
    '_blank',
    'noopener,noreferrer'
  )
}
onMounted(() => {
  void load()
  window.addEventListener('focus', refreshVisible)
  document.addEventListener('visibilitychange', refreshVisible)
})
onBeforeUnmount(() => {
  guard.invalidate()
  window.removeEventListener('focus', refreshVisible)
  document.removeEventListener('visibilitychange', refreshVisible)
})
</script>
<template>
  <section
    v-if="!disabled"
    aria-labelledby="continue-watching-title"
    class="relative z-10 px-4 pb-12 max-w-7xl mx-auto w-full"
  >
    <header class="flex items-center justify-between gap-3 mb-4">
      <div>
        <h2 id="continue-watching-title" class="text-primary text-xl font-semibold">继续观看</h2>
        <p class="text-muted text-sm mt-1">当前账号在各设备上保存的最近进度</p>
      </div>
      <AppButton variant="neutral" size="sm" :loading="loading" @click="load">刷新</AppButton>
    </header>
    <PageLoad v-if="loading && !items.length" text="正在读取播放进度" />
    <RequestError v-if="error" :message="error" @retry="load" />
    <EmptyState
      v-if="!loading && !error && !items.length"
      compact
      class="py-6"
      icon="empty"
      title="暂无可接续记录"
      description="播放视频后会自动保存进度。"
    />
    <ul v-if="items.length" class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <li
        v-for="item in items"
        :key="item.avid"
        class="rounded-xl bg-secondary border border-[var(--border-color)] overflow-hidden"
      >
        <ResourceCover
          :url="resourceApi.getCoverUrl(item.avid, 'small')"
          :title="resolveResourceTitle(item, settings.displayTitle) || item.avid"
          class="aspect-video rounded-none"
        />
        <div class="p-4 space-y-3">
          <div>
            <p class="text-muted text-xs">
              {{ item.avid }} · {{ item.mode === 'local' ? '本地视频' : '源站视频' }}
            </p>
            <h3 class="text-primary font-medium line-clamp-2 mt-1">
              {{ resolveResourceTitle(item, settings.displayTitle) || item.avid }}
            </h3>
          </div>
          <div class="text-muted text-sm">
            {{ time(item.position_seconds) }} / {{ time(item.duration_seconds)
            }}<span v-if="item.restore_policy === 'confirm'" class="block text-xs mt-1"
              >接续前需确认当前来源视频</span
            >
          </div>
          <progress
            class="w-full h-1.5 accent-[var(--accent-primary)]"
            :value="item.position_seconds"
            :max="item.duration_seconds"
            :aria-label="`${item.avid} 播放进度`"
          />
          <AppButton class="w-full" @click="open(item)">继续播放</AppButton>
        </div>
      </li>
    </ul>
  </section>
</template>
<style scoped>
progress {
  appearance: none;
  border: 0;
  border-radius: 1rem;
  overflow: hidden;
  background: var(--bg-primary);
  color: var(--accent-primary);
}
progress::-webkit-progress-bar {
  background: var(--bg-primary);
}
progress::-webkit-progress-value {
  background: var(--accent-primary);
}
progress::-moz-progress-bar {
  background: var(--accent-primary);
}
</style>
