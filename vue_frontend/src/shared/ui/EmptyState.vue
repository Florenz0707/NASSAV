<script setup>
import AppIcon from './AppIcon.vue'
defineProps({
  compact: Boolean,
  icon: {
    type: String,
    default: 'empty',
  },
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <div
    class="flex flex-col items-center justify-center text-center"
    :class="compact ? 'p-0' : 'py-16 px-8'"
  >
    <div class="text-6xl text-muted mb-6">
      <slot name="icon"><AppIcon :name="icon" class="w-14 h-14" /></slot>
    </div>
    <h3 class="text-xl font-semibold text-primary mb-2">
      {{ title }}
    </h3>
    <p v-if="description" class="text-[0.95rem] text-muted max-w-[400px] leading-relaxed">
      {{ description }}
    </p>
    <div v-if="$slots.action" class="mt-6">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}
</style>
