<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { playbackApi } from '../../../api/playback.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import { createPlaybackSession } from '../lib/playbackSession.js'
import { attachPlayer } from '../lib/mediaPlayer.js'

const props = defineProps({
  active: Boolean,
  avid: { type: String, required: true },
})
const video = ref(null)
const state = ref({ state: 'queued' }),
  mediaError = ref(''),
  buffering = ref(false)
let destroyPlayer = null,
  playerVersion = 0,
  position = 0,
  previousAvid = '',
  resumePlayback = false
const session = createPlaybackSession({
  api: playbackApi,
  changed: (row) => {
    state.value = row
  },
})
const preparing = computed(() => ['queued', 'resolving'].includes(state.value.state))
function releasePlayer() {
  playerVersion++
  if (destroyPlayer && video.value) resumePlayback = !video.value.paused
  if (destroyPlayer && video.value) position = video.value.currentTime || position
  destroyPlayer?.()
  destroyPlayer = null
  buffering.value = false
}
async function retry() {
  releasePlayer()
  mediaError.value = ''
  if (state.value.error_code === 'media_identity_changed') position = 0
  resumePlayback = false
  await session.start(props.avid)
}
watch(
  () => [props.active, props.avid],
  ([show, avid]) => {
    releasePlayer()
    mediaError.value = ''
    if (avid !== previousAvid) position = 0
    previousAvid = avid
    if (show) session.start(avid)
    else session.stop()
  },
  { immediate: true }
)
watch(
  () => state.value.manifest_url,
  async (url) => {
    if (!url || !props.active) {
      releasePlayer()
      return
    }
    if (destroyPlayer) releasePlayer()
    const token = playerVersion
    mediaError.value = ''
    await nextTick()
    if (token !== playerVersion || !video.value) return
    try {
      const dispose = await attachPlayer(video.value, url, {
        position,
        resume: state.value.refresh_count === 1 && resumePlayback,
        current: () => token === playerVersion && props.active,
        failed: (message, status = 0) => {
          if (token === playerVersion) {
            if (status === 410 && state.value.refresh_count !== 1) {
              const wasPlaying = video.value && !video.value.paused
              releasePlayer()
              resumePlayback = wasPlaying
              const refreshToken = playerVersion
              session.refresh().then((ok) => {
                if (!ok && refreshToken === playerVersion && props.active)
                  mediaError.value = message
              })
            } else {
              buffering.value = false
              mediaError.value = message
            }
          }
        },
      })
      if (token !== playerVersion) dispose()
      else destroyPlayer = dispose
    } catch {
      if (token === playerVersion) mediaError.value = '当前浏览器不支持在线播放'
    }
  }
)
function leave() {
  releasePlayer()
  session.stop(true)
}
window.addEventListener('pagehide', leave)
onBeforeUnmount(() => {
  window.removeEventListener('pagehide', leave)
  releasePlayer()
  session.dispose()
})
</script>
<template>
  <section
    v-if="active"
    aria-label="视频播放器"
    class="relative w-full aspect-video overflow-hidden rounded-2xl border border-[var(--border-color)] bg-primary"
  >
    <div v-if="preparing" class="absolute inset-0 flex items-center justify-center p-4">
      <PageLoad variant="spinner" text="正在准备播放，来源获取可能需要一分钟" />
    </div>
    <video
      v-if="state.state === 'ready'"
      ref="video"
      controls
      playsinline
      preload="metadata"
      class="absolute inset-0 w-full h-full object-contain"
      aria-label="在线播放"
      @waiting="buffering = true"
      @canplay="buffering = false"
      @playing="buffering = false"
      @pause="buffering = false"
    />
    <p
      v-if="buffering && !mediaError"
      role="status"
      class="absolute inset-0 flex items-center justify-center pointer-events-none text-secondary text-sm"
    >
      正在缓冲…
    </p>
    <div
      v-if="mediaError || ['failed', 'closed'].includes(state.state)"
      class="absolute inset-0 flex flex-col items-center justify-center gap-4 p-4 bg-primary/90 overflow-y-auto"
    >
      <p role="alert" class="text-secondary text-sm text-center">
        {{ mediaError || state.message }}
      </p>
      <AppButton @click="retry">重试播放</AppButton>
    </div>
  </section>
</template>
