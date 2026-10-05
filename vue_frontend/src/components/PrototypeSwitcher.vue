<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppButton from './AppButton.vue'
const props = defineProps({
  variants: { type: Array, required: true },
  current: { type: String, required: true },
})
const development = import.meta.env.DEV
const route = useRoute(),
  router = useRouter()
function cycle(delta) {
  const index = Math.max(
    0,
    props.variants.findIndex((v) => v.value === props.current)
  )
  router.replace({
    query: {
      ...route.query,
      variant:
        props.variants[(index + delta + props.variants.length) % props.variants.length].value,
    },
  })
}
function keydown(event) {
  if (
    event.target.closest(
      'input, textarea, select, [contenteditable], [role="combobox"], [role="dialog"]'
    )
  )
    return
  if (['ArrowLeft', 'ArrowRight'].includes(event.key)) {
    event.preventDefault()
    cycle(event.key === 'ArrowLeft' ? -1 : 1)
  }
}
onMounted(() => window.addEventListener('keydown', keydown))
onBeforeUnmount(() => window.removeEventListener('keydown', keydown))
</script>
<template>
  <div
    v-if="development"
    class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-secondary border rounded-full p-3 shadow-lg border-[var(--border-color)]"
    aria-label="Demo 布局切换"
  >
    <AppButton size="sm" variant="neutral" aria-label="上一种布局" @click="cycle(-1)">←</AppButton>
    <span class="text-primary whitespace-nowrap text-sm">{{
      variants.find((v) => v.value === current)?.label
    }}</span>
    <AppButton size="sm" variant="neutral" aria-label="下一种布局" @click="cycle(1)">→</AppButton>
  </div>
</template>
