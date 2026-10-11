<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { playbackApi } from '../../../api/playback.js'
import { useDialog } from '../../../shared/composables/useDialog.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import { createPlaybackSession } from '../lib/playbackSession.js'
import { attachPlayer } from '../lib/mediaPlayer.js'

const props = defineProps({
  show: Boolean,
  avid: { type: String, required: true },
  title: { type: String, default: '' },
})
const emit = defineEmits(['update:show'])
const visible = computed(() => props.show),
  root = ref(null),
  video = ref(null)
const state = ref({ state: 'queued' }),
  mediaError = ref(''),
  buffering = ref(false)
const close = () => emit('update:show', false)
const { titleId } = useDialog(visible, root, close)
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
  () => [props.show, props.avid],
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
    if (!url || !props.show) {
      releasePlayer()
      return
    }
    if (destroyPlayer) releasePlayer()
    const token = playerVersion
    await nextTick()
    if (token !== playerVersion || !video.value) return
    try {
      const dispose = await attachPlayer(video.value, url, {
        position,
        resume: state.value.refresh_count === 1 && resumePlayback,
        current: () => token === playerVersion && props.show,
        failed: (message, status = 0) => {
          if (token === playerVersion) {
            if (status === 410 && state.value.refresh_count !== 1) {
              const wasPlaying = video.value && !video.value.paused
              releasePlayer()
              resumePlayback = wasPlaying
              const refreshToken = playerVersion
              session.refresh().then((ok) => {
                if (!ok && refreshToken === playerVersion && props.show) mediaError.value = message
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
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 z-[10000] bg-black/80 backdrop-blur flex items-center justify-center p-4"
      @click.self="close"
    >
      <section
        ref="root"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        class="bg-secondary text-primary border rounded-2xl shadow-xl w-full max-w-5xl max-h-[90dvh] overflow-y-auto p-4 sm:p-6"
      >
        <header class="flex items-center justify-between gap-4 mb-4">
          <h2 :id="titleId" class="text-lg font-semibold truncate">{{ title || avid }}</h2>
          <AppButton variant="neutral" size="sm" aria-label="关闭播放器" @click="close">
            <svg
              class="w-5 h-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              aria-hidden="true"
            >
              <path d="m6 6 12 12M6 18 18 6" />
            </svg>
          </AppButton>
        </header>
        <div class="min-h-48 flex flex-col justify-center">
          <PageLoad
            v-if="preparing"
            variant="spinner"
            text="正在准备播放，来源获取可能需要一分钟"
          />
          <template v-if="state.state === 'ready'">
            <video
              ref="video"
              controls
              playsinline
              preload="metadata"
              class="w-full max-h-[65dvh] rounded-xl bg-primary"
              aria-label="在线播放"
              @waiting="buffering = true"
              @canplay="buffering = false"
              @playing="buffering = false"
              @pause="buffering = false"
            />
            <p v-if="buffering && !mediaError" role="status" class="text-muted text-sm mt-3">
              正在缓冲…
            </p>
          </template>
          <div
            v-if="mediaError || ['failed', 'closed'].includes(state.state)"
            class="flex flex-col items-center gap-4 py-6"
          >
            <p role="alert" class="text-secondary text-sm">{{ mediaError || state.message }}</p>
            <AppButton @click="retry">重试播放</AppButton>
          </div>
        </div>
        <p class="text-muted text-xs mt-4">
          在线播放不保存视频文件。暂停保留会话，关闭播放器释放会话。
        </p>
      </section>
    </div>
  </Teleport>
</template>
