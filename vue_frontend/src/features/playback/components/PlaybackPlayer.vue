<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { playbackApi } from '../../../api/playback.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import { createPlaybackSession } from '../lib/playbackSession.js'
import { createPlaybackProgress } from '../lib/playbackProgress.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { bindPlaybackPreferences } from '../lib/playbackPreferences.js'
import { createViewingRecorder } from '../lib/viewingRecorder.js'
import { attachPlayer } from '../lib/mediaPlayer.js'

const props = defineProps({
  active: Boolean,
  avid: { type: String, required: true },
  mode: { type: String, default: 'source' },
})
const settings = useSettingsStore()
const preferenceMessage = ref('')
const historyMessage = ref('')
const history = createViewingRecorder({
  record: playbackApi.viewed,
  changed: (message) => {
    historyMessage.value = message
  },
})
let releasePreferences = null
const video = ref(null)
const progressState = ref({ candidate: null, message: '' })
const progress = createPlaybackProgress({
  api: playbackApi,
  changed: (value) => {
    progressState.value = value
  },
})
const resumeTime = computed(() => {
  const seconds = Math.floor(progressState.value.candidate?.position_seconds || 0)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
})
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
  history.detach()
  releasePreferences?.()
  releasePreferences = null
  preferenceMessage.value = ''
  void progress.detach()
  progressState.value = { candidate: null, message: '' }
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
  if (props.mode === 'local' || state.value.error_code === 'media_identity_changed') position = 0
  resumePlayback = false
  await session.start(props.avid, props.mode)
}
watch(
  () => [props.active, props.avid, props.mode],
  ([show, avid, mode]) => {
    releasePlayer()
    mediaError.value = ''
    if (`${avid}:${mode}` !== previousAvid) position = 0
    previousAvid = `${avid}:${mode}`
    if (show) session.start(avid, mode)
    else session.stop()
  },
  { immediate: true }
)
watch(
  () => state.value.media_url || state.value.manifest_url,
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
      releasePreferences = bindPlaybackPreferences(video.value, {
        preferences: settings.playbackPreferences,
        save: settings.playbackPreferenceWriter(),
        current: () => token === playerVersion && props.active,
        failed: () => {
          if (token === playerVersion)
            preferenceMessage.value = '播放偏好保存失败，可在个人设置中重试'
        },
      })
      history.bind(state.value, video.value)
      void progress.bind(state.value, video.value)
      if (token !== playerVersion || !props.active) return
      const dispose = await attachPlayer(video.value, url, {
        position,
        subtitlesEnabled: settings.playbackPreferences.subtitles_enabled,
        mediaType: state.value.media_type || 'hls',
        resume: state.value.refresh_count === 1 && resumePlayback,
        current: () => token === playerVersion && props.active,
        failed: (message, status = 0) => {
          if (token === playerVersion) {
            if (props.mode === 'source' && status === 410 && state.value.refresh_count !== 1) {
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
  const saving = progress.detach(true)
  releasePlayer()
  if (!saving.closesSession) session.stop(true)
  else void saving.finally(() => session.stop(true))
}
function hide() {
  if (document.visibilityState === 'hidden') void progress.flush(true)
}
document.addEventListener('visibilitychange', hide)
window.addEventListener('pagehide', leave)
onBeforeUnmount(() => {
  window.removeEventListener('pagehide', leave)
  document.removeEventListener('visibilitychange', hide)
  const saving = progress.detach(true)
  releasePlayer()
  if (!saving.closesSession) session.dispose()
  else void saving.finally(() => session.dispose())
})
</script>
<template>
  <section
    v-if="active"
    aria-label="视频播放器"
    class="relative w-full aspect-video overflow-hidden rounded-2xl border border-[var(--border-color)] bg-primary"
  >
    <div v-if="preparing" class="absolute inset-0 flex items-center justify-center p-4">
      <PageLoad
        variant="spinner"
        :text="mode === 'local' ? '正在读取已下载视频' : '正在准备播放，来源获取可能需要一分钟'"
      />
    </div>
    <video
      v-if="state.state === 'ready'"
      ref="video"
      controls
      playsinline
      preload="metadata"
      class="absolute inset-0 w-full h-full object-contain"
      :aria-label="mode === 'local' ? '本地视频播放' : '在线播放'"
      @waiting="buffering = true"
      @canplay="buffering = false"
      @playing="buffering = false"
      @pause="buffering = false"
    />
    <div
      v-if="(progressState.candidate || progressState.takeover) && !mediaError"
      class="absolute inset-0 flex flex-col items-center justify-start sm:justify-center gap-4 p-4 bg-primary/90 overflow-y-auto"
      role="group"
      aria-label="恢复播放进度"
    >
      <p class="text-primary text-sm text-center shrink-0">
        <span v-if="progressState.candidate"
          >上次播放至 {{ resumeTime
          }}{{
            progressState.candidate.restore_policy === 'confirm'
              ? '，请确认当前来源视频是否适用'
              : ''
          }}</span
        >
        <span v-if="progressState.takeover" class="block mt-2"
          >另一播放页面持有保存权，接续后将由本页保存进度。</span
        >
      </p>
      <div class="flex flex-wrap justify-center gap-3 shrink-0">
        <AppButton :loading="progressState.choosing" @click="progress.choose(true)">{{
          progressState.takeover ? '在此接续' : '继续上次播放'
        }}</AppButton>
        <AppButton
          variant="neutral"
          :disabled="progressState.choosing"
          @click="progress.choose(false)"
          >从头播放</AppButton
        >
        <AppButton
          v-if="progressState.takeover"
          variant="neutral"
          :disabled="progressState.choosing"
          @click="progress.playWithoutSaving()"
          >仅播放，不保存进度</AppButton
        >
      </div>
    </div>
    <div
      v-if="(progressState.message || preferenceMessage || historyMessage) && !mediaError"
      role="status"
      class="absolute top-2 left-2 right-2 rounded-lg bg-secondary p-2 text-muted text-xs"
    >
      {{ progressState.message || preferenceMessage || historyMessage }}
      <AppButton
        v-if="historyMessage"
        size="sm"
        variant="neutral"
        class="ml-2"
        @click="history.retry()"
        >重试记录</AppButton
      >
      <AppButton
        v-if="progressState.canTakeover"
        variant="neutral"
        size="sm"
        class="ml-2"
        :loading="progressState.choosing"
        @click="progress.choose(true)"
        >在此接续保存</AppButton
      >
    </div>
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
