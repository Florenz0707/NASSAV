<script setup>
defineProps({
  show: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: '',
  },
  maxWidthClass: {
    type: String,
    default: 'max-w-2xl',
  },
})

const emit = defineEmits(['close'])
</script>

<template>
  <div
    v-if="show"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
  >
    <div
      class="rounded-2xl w-full overflow-hidden shadow-2xl tw-surface-overlay"
      :class="maxWidthClass"
    >
      <div
        class="p-6 flex justify-between items-center"
        style="border-bottom: 1px solid var(--border-color)"
      >
        <h3 class="text-xl font-bold text-[var(--text-primary)]">{{ title }}</h3>
        <button
          class="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <div class="p-6">
        <slot />
      </div>

      <div class="p-6" style="border-top: 1px solid var(--border-color)">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>
