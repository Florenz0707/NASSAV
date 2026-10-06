<script setup>
// Existing resource images, with an error placeholder and optional debug artwork.
import { ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
const props = defineProps({
  url: { type: String, default: '' },
  scene: { type: String, default: '' },
  title: { type: String, default: '' },
  imageClass: { type: String, default: 'object-cover' },
})
const failed = ref(false)
watch(
  () => props.url,
  () => {
    failed.value = false
  }
)
</script>
<template>
  <div class="rounded-lg overflow-hidden bg-primary">
    <img
      v-if="url && !failed"
      :src="url"
      :alt="title + ' · 资源封面'"
      loading="lazy"
      class="w-full h-full"
      :class="imageClass"
      @error="failed = true"
    />
    <svg
      v-else-if="scene"
      class="w-full h-full"
      viewBox="0 0 320 180"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      :aria-label="title + ' · 示例封面'"
    >
      <rect width="320" height="180" class="sky" />
      <circle cx="246" cy="42" r="23" class="sun" />
      <template v-if="scene === 'city'">
        <path d="M0 180V90h36V55h38v75h25V76h46v104h28V45h42v135h32V88h43v92Z" class="land" />
        <path d="M12 180 140 115h24L308 180Z" class="foreground" />
      </template>
      <template v-else-if="scene === 'coast'">
        <path d="M0 100Q80 84 160 101T320 98V180H0Z" class="land" />
        <path d="M0 156Q150 111 320 156V180H0Z" class="foreground" />
      </template>
      <template v-else>
        <path d="M0 180V132L82 38l82 106 49-65 107 79v22Z" class="land" />
        <path d="M0 180V153l54-50 61 66 82-52 123 45v18Z" class="foreground" />
        <path
          v-if="scene === 'forest'"
          d="m30 132 18-54 18 54Zm67 25 21-71 21 71Zm144 9 22-78 22 78Z"
          class="trees"
        />
      </template>
      <text x="16" y="164" class="caption" font-size="12">DEMO COVER</text>
    </svg>
    <div
      v-else
      class="flex flex-col items-center justify-center w-full h-full text-muted gap-1"
      role="img"
      aria-label="封面尚未获取"
    >
      <AppIcon name="empty" /><span class="text-xs">待获取封面</span>
    </div>
  </div>
</template>
<style scoped>
.sky {
  fill: var(--bg-secondary);
}
.sun {
  fill: var(--accent-warning);
}
.land {
  fill: var(--accent-secondary);
}
.foreground {
  fill: var(--accent-primary);
}
.trees {
  fill: var(--accent-tertiary);
}
.caption {
  fill: var(--on-accent);
}
</style>
