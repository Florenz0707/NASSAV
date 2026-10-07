<script setup>
import AppIcon from '../../../shared/ui/AppIcon.vue'
defineProps({
  items: {
    type: Array,
    required: true,
  },
  activeId: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['select'])
</script>

<template>
  <div class="tw-surface-overlay rounded-xl p-2">
    <button
      type="button"
      v-for="item in items"
      :key="item.id"
      class="w-full flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-all duration-200"
      :style="
        activeId === item.id
          ? 'background: color-mix(in srgb, var(--accent-primary) 10%, transparent); color: var(--accent-primary-text);'
          : 'color: var(--text-muted);'
      "
      @click="emit('select', item.id)"
    >
      <AppIcon :name="item.icon" />
      <span class="font-medium">{{ item.name }}</span>
    </button>
  </div>
</template>
