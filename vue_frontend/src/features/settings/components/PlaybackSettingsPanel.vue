<script setup>
import CustomSelect from '../../../shared/ui/CustomSelect.vue'
import AppButton from '../../../shared/ui/AppButton.vue'
const props = defineProps({
  modelValue: { type: Object, required: true },
  headingTag: { type: String, default: 'h3', validator: (value) => ['h2', 'h3'].includes(value) },
})
const emit = defineEmits(['update:modelValue'])
function update(field, value) {
  emit('update:modelValue', { ...props.modelValue, [field]: value })
}
const rates = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2].map((value) => ({ value, label: `${value}×` }))
const modes = [
  { value: 'auto', label: '优先已下载视频' },
  { value: 'local', label: '仅本地视频' },
  { value: 'source', label: '源站在线播放' },
]
</script>
<template>
  <section
    aria-labelledby="playback-settings-title"
    class="p-4 rounded-xl bg-surface-subtle/[0.02] border border-[var(--border-white-5)] space-y-4"
  >
    <component
      :is="headingTag"
      id="playback-settings-title"
      class="text-sm font-medium text-muted uppercase tracking-wider"
      >默认播放偏好</component
    >
    <div
      class="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-[var(--border-white-5)]"
    >
      <label for="playback-volume" class="text-primary">默认音量 </label>
      <div class="flex items-center gap-4">
        <input
          id="playback-volume"
          type="range"
          min="0"
          max="1"
          step="0.01"
          :value="modelValue.volume"
          class="w-50 accent-[var(--accent-primary)]"
          @input="update('volume', Number($event.target.value))"
        />
        <span>{{ Math.round(modelValue.volume * 100) }} %</span>
      </div>
    </div>
    <div
      class="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-[var(--border-white-5)]"
    >
      <span class="text-primary">默认静音</span>
      <AppButton
        variant="neutral"
        role="switch"
        aria-label="默认静音"
        :aria-checked="modelValue.muted"
        @click="update('muted', !modelValue.muted)"
        >{{ modelValue.muted ? '已开启' : '已关闭' }}</AppButton
      >
    </div>
    <div
      class="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-[var(--border-white-5)]"
    >
      <label for="playback-rate" class="text-primary">默认倍速</label>
      <CustomSelect
        id="playback-rate"
        aria-label="默认倍速"
        :model-value="modelValue.rate"
        :options="rates"
        class="min-w-[10rem]"
        @update:model-value="update('rate', $event)"
      />
    </div>
    <div
      class="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-[var(--border-white-5)]"
    >
      <span class="text-primary">显示字幕（视频提供字幕时）</span>
      <AppButton
        variant="neutral"
        role="switch"
        aria-label="默认显示字幕"
        :aria-checked="modelValue.subtitles_enabled"
        @click="update('subtitles_enabled', !modelValue.subtitles_enabled)"
        >{{ modelValue.subtitles_enabled ? '已开启' : '已关闭' }}</AppButton
      >
    </div>
    <div
      class="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-[var(--border-white-5)]"
    >
      <label for="playback-mode" class="text-primary">默认播放模式</label>
      <CustomSelect
        id="playback-mode"
        aria-label="默认播放模式"
        :model-value="modelValue.default_mode"
        :options="modes"
        class="min-w-[12rem]"
        @update:model-value="update('default_mode', $event)"
      />
    </div>
  </section>
</template>
