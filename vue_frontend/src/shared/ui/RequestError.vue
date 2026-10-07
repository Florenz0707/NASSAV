<script setup>
import AppButton from './AppButton.vue'
import EmptyState from './EmptyState.vue'
import AppIcon from './AppIcon.vue'
defineProps({
  message: { type: String, required: true },
  title: { type: String, default: '加载失败' },
  compact: Boolean,
  retrying: Boolean,
})
defineEmits(['retry'])
</script>
<template>
  <div
    v-if="compact"
    role="alert"
    class="flex flex-wrap items-center gap-3 p-4 mb-4 rounded-xl bg-secondary border border-[var(--border-color)]"
  >
    <AppIcon name="warning" class="w-5 h-5 text-accent-danger shrink-0" />
    <p class="text-secondary flex-1">{{ message }}</p>
    <AppButton variant="neutral" size="sm" :loading="retrying" @click="$emit('retry')"
      >重试</AppButton
    >
  </div>
  <EmptyState v-else role="alert" icon="warning" :title="title" :description="message">
    <template #action
      ><AppButton variant="neutral" :loading="retrying" @click="$emit('retry')"
        >重试</AppButton
      ></template
    >
  </EmptyState>
</template>
