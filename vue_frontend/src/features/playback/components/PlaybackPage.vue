<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { resourceApi } from '../../../api/resources.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { playbackMode } from '../lib/playbackPreferences.js'
import PageLoad from '../../../shared/ui/PageLoad.vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import PlaybackPlayer from './PlaybackPlayer.vue'

const props = defineProps({
  avid: { type: String, required: true },
  mode: { type: String, default: 'auto' },
})
const settings = useSettingsStore()
const metadata = ref(null)
const guard = createRequestGuard()
const settingsReady = ref(false)
settings.loadSettings().then(() => {
  settingsReady.value = true
})
const metadataReady = ref(false)
const effectiveMode = computed(() => {
  if (!settingsReady.value || !metadataReady.value) return null
  return playbackMode(
    props.mode,
    settings.playbackPreferences.default_mode,
    metadata.value?.file_exists
  )
})
const title = computed(
  () => resolveResourceTitle(metadata.value, settings.displayTitle) || props.avid
)
watch(
  () => props.avid,
  async (avid) => {
    const token = guard.begin()
    metadata.value = null
    metadataReady.value = false
    try {
      const response = await resourceApi.getMetadata(avid)
      if (guard.current(token)) metadata.value = response.data
    } catch {
      // Metadata is optional display information; playback reports its own errors.
    } finally {
      if (guard.current(token)) metadataReady.value = true
    }
  },
  { immediate: true }
)
onBeforeUnmount(() => guard.invalidate())
</script>

<template>
  <section class="w-full max-w-5xl mx-auto">
    <header class="text-left mb-4">
      <p class="text-muted text-sm mb-2">
        {{ avid }} · {{ effectiveMode === 'local' ? '本地播放' : '在线播放' }}
      </p>
      <h1 class="text-primary text-xl font-semibold break-words">{{ title }}</h1>
    </header>
    <PlaybackPlayer v-if="effectiveMode" active :avid="avid" :mode="effectiveMode" />
    <div
      v-else
      class="relative w-full aspect-video rounded-2xl bg-primary flex items-center justify-center"
    >
      <PageLoad variant="spinner" text="正在读取播放设置" />
    </div>
  </section>
</template>
