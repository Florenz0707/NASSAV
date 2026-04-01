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
  showClose: {
    type: Boolean,
    default: true,
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
        <button v-if="showClose" class="settings-modal-close-btn" @click="emit('close')">✕</button>
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

<style scoped>
.settings-modal-close-btn {
  display: inline-flex;
  min-width: 2.35rem;
  min-height: 2.35rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid rgba(255, 107, 107, 0.22);
  background: rgba(255, 107, 107, 0.08);
  color: var(--accent-primary);
  font-size: 1rem;
  line-height: 1;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.settings-modal-close-btn:hover {
  transform: translateY(-1px);
  border-color: rgba(255, 107, 107, 0.42);
  background: rgba(255, 107, 107, 0.14);
}
</style>
