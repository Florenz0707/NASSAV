<script setup>
import { ref, toRef } from 'vue'
import { useDialog } from '../../composables/useDialog.js'
const props = defineProps({
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
const dialogRef = ref(null)
const { titleId } = useDialog(toRef(props, 'show'), dialogRef, () => emit('close'))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 z-[10000] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
    >
      <div
        ref="dialogRef"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        class="rounded-2xl w-full overflow-hidden shadow-2xl tw-surface-overlay"
        :class="maxWidthClass"
      >
        <div
          class="p-6 flex justify-between items-center"
          style="border-bottom: 1px solid var(--border-color)"
        >
          <div class="settings-modal-header-main">
            <h3 :id="titleId" class="text-xl font-bold text-[var(--text-primary)]">{{ title }}</h3>
            <slot name="header-extra" />
          </div>
          <button
            v-if="showClose"
            class="settings-modal-close-btn"
            aria-label="关闭弹窗"
            @click="emit('close')"
          >
            <svg
              class="w-5 h-5 flex items-center"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              ></path>
            </svg>
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
  </Teleport>
</template>

<style scoped>
.settings-modal-header-main {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.settings-modal-close-btn {
  display: inline-flex;
  min-width: 2.35rem;
  min-height: 2.35rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent-primary) 22%, transparent);
  background: color-mix(in srgb, var(--accent-primary) 8%, transparent);
  color: var(--accent-primary);
  background: theme('backgroundColor.accent-primary/10');
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
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent-primary) 42%, transparent);
  background: color-mix(in srgb, var(--accent-primary) 14%, transparent);
  background: theme('backgroundColor.accent-primary/20');
}
</style>
