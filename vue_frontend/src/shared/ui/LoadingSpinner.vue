<script setup>
defineProps({ size: { type: String, default: 'medium' }, text: { type: String, default: '' } })
</script>
<template>
  <div class="loading-indicator flex items-center justify-center" :class="size">
    <span class="spinner" aria-hidden="true" />
    <p v-if="text" class="text-sm ml-3">{{ text }}</p>
  </div>
</template>
<style scoped>
.loading-indicator {
  color: var(--text-secondary);
}
.spinner {
  display: inline-block;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border: 2px solid color-mix(in srgb, currentColor 20%, transparent);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: loading-turn 1.5s linear infinite;
}
.small .spinner {
  width: 14px;
  height: 14px;
}
.large .spinner {
  width: 40px;
  height: 40px;
  border-width: 3px;
}
@keyframes loading-turn {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
</style>
