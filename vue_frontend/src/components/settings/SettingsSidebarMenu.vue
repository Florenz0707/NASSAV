<script setup>
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
    <div
      v-for="item in items"
      :key="item.id"
      class="flex items-center gap-3 px-4 py-3 rounded-lg cursor-pointer transition-all duration-200"
      :style="
        activeId === item.id
          ? 'background: color-mix(in srgb, var(--accent-primary) 10%, transparent); color: var(--accent-primary);'
          : 'color: var(--text-muted);'
      "
      @click="emit('select', item.id)"
    >
      <span class="text-xl">{{ item.icon }}</span>
      <span class="font-medium">{{ item.name }}</span>
    </div>
  </div>
</template>
