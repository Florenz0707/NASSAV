<script setup>
import { ref } from 'vue'
import AppButton from './AppButton.vue'
import { useDialog } from '../composables/useDialog.js'

defineProps({
  title: { type: String, required: true },
  label: { type: String, required: true },
  buttonText: { type: String, default: '' },
  disabled: Boolean,
  loading: Boolean,
})
const visible = ref(false)
const root = ref(null)
const close = () => {
  visible.value = false
}
const { titleId } = useDialog(visible, root, close)
</script>
<template>
  <AppButton
    variant="neutral"
    size="m"
    :class="buttonText ? 'flex' : 'w-8 h-8 p-0 shrink-0'"
    :disabled="disabled"
    :loading="loading"
    :aria-label="label"
    aria-haspopup="dialog"
    :aria-expanded="visible"
    :aria-controls="visible ? `${titleId}-panel` : undefined"
    @click="visible = true"
  >
    <span v-if="buttonText">{{ buttonText }}</span>
    <svg
      class="w-4 h-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7h.01" />
    </svg>
  </AppButton>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-[10000] bg-black/80 backdrop-blur flex items-center justify-center p-4"
      @click.self="close"
    >
      <section
        ref="root"
        :id="`${titleId}-panel`"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
        class="bg-secondary text-primary border border-[var(--border-color)] rounded-2xl shadow-xl w-full max-w-3xl max-h-[85dvh] overflow-y-auto p-5"
      >
        <header class="flex items-center justify-between gap-3 mb-4">
          <h2 :id="titleId" class="text-xl font-semibold">{{ title }}</h2>
          <AppButton
            variant="neutral"
            size="sm"
            class="w-8 h-8 p-0 shrink-0"
            aria-label="关闭信息弹窗"
            @click="close"
            ><svg
              class="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              aria-hidden="true"
            >
              <path d="m6 6 12 12M6 18 18 6" /></svg
          ></AppButton>
        </header>
        <slot />
      </section>
    </div>
  </Teleport>
</template>
