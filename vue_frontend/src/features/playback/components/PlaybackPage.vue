<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { resourceApi } from '../../../api/resources.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import PlaybackPlayer from './PlaybackPlayer.vue'

const props = defineProps({
  avid: { type: String, required: true },
  mode: { type: String, default: 'source' },
})
const settings = useSettingsStore()
const metadata = ref(null)
const guard = createRequestGuard()
const title = computed(
  () => resolveResourceTitle(metadata.value, settings.displayTitle) || props.avid
)
watch(
  () => props.avid,
  async (avid) => {
    const token = guard.begin()
    metadata.value = null
    try {
      const response = await resourceApi.getMetadata(avid)
      if (guard.current(token)) metadata.value = response.data
    } catch {
      // Metadata is optional display information; playback reports its own errors.
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
        {{ avid }} · {{ mode === 'local' ? '本地播放' : '在线播放' }}
      </p>
      <h1 class="text-primary text-xl font-semibold break-words">{{ title }}</h1>
    </header>
    <PlaybackPlayer active :avid="avid" :mode="mode" />
  </section>
</template>
