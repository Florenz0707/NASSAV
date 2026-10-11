<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { resourceApi } from '../../../api/resources.js'
import { useSettingsStore } from '../../settings/stores/settings.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import AppButton from '../../../shared/ui/AppButton.vue'
import PlaybackPlayer from './PlaybackPlayer.vue'

const props = defineProps({ avid: { type: String, required: true } })
const settings = useSettingsStore()
const metadata = ref(null),
  active = ref(true)
const guard = createRequestGuard()
const title = computed(
  () => resolveResourceTitle(metadata.value, settings.displayTitle) || props.avid
)
watch(
  () => props.avid,
  async (avid) => {
    const token = guard.begin()
    metadata.value = null
    active.value = true
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
  <section class="max-w-5xl mx-auto">
    <header class="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div class="min-w-0 flex-1">
        <p class="text-muted text-sm mb-2">{{ avid }} · 在线播放</p>
        <h1 class="text-primary text-xl font-semibold break-words">{{ title }}</h1>
      </div>
      <AppButton :variant="active ? 'neutral' : 'primary'" @click="active = !active">
        {{ active ? '停止播放' : '重新播放' }}
      </AppButton>
    </header>
    <div class="bg-secondary border border-[var(--border-color)] rounded-2xl p-4 sm:p-6">
      <PlaybackPlayer :active="active" :avid="avid" />
      <p v-if="!active" role="status" class="text-secondary text-center py-16">播放已停止</p>
    </div>
    <RouterLink
      :to="{ name: 'ResourceDetail', params: { avid } }"
      class="inline-block mt-6 text-accent-primary underline underline-offset-4"
    >
      查看资源详情
    </RouterLink>
  </section>
</template>
