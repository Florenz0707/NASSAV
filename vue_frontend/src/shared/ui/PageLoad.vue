<script setup>
import { onBeforeUnmount, ref } from 'vue'
import LoadingSpinner from './LoadingSpinner.vue'
defineProps({
  variant: { type: String, default: 'resources' },
  count: { type: Number, default: 6 },
  text: { type: String, default: '正在加载' },
})
const visible = ref(false)
const timer = setTimeout(() => {
  visible.value = true
}, 1000)
onBeforeUnmount(() => clearTimeout(timer))
</script>
<template>
  <div
    class="page-load"
    :class="{ 'page-load--compact': variant === 'spinner', 'page-load--pending': !visible }"
    role="status"
    aria-live="polite"
    aria-busy="true"
  >
    <span class="sr-only">{{ text }}</span>
    <template v-if="visible">
      <LoadingSpinner v-if="variant === 'spinner'" size="large" :text="text" />
      <div
        v-else-if="variant === 'detail'"
        class="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-10"
        aria-hidden="true"
      >
        <div class="skeleton h-[310px] rounded-2xl" />
        <div class="space-y-6">
          <div class="skeleton h-8 rounded w-3/4" />
          <div v-for="i in 5" :key="i" class="skeleton h-5 rounded w-2/3" />
        </div>
      </div>
      <div
        v-else
        class="library-grid gap-6"
        :class="variant === 'directory' ? '' : 'resource-library-grid'"
        aria-hidden="true"
      >
        <div
          v-for="i in count"
          :key="i"
          class="page-skeleton rounded-2xl border border-[var(--border-color)] p-4 bg-secondary"
        >
          <div
            class="skeleton rounded-xl"
            :class="variant === 'directory' ? 'aspect-square' : 'aspect-[4/3]'"
          />
          <div class="skeleton h-4 rounded mt-4 w-3/4" />
          <div class="skeleton h-3 rounded mt-3 w-1/2" />
          <div v-if="variant !== 'directory'" class="skeleton h-10 rounded-lg mt-6" />
        </div>
      </div>
    </template>
  </div>
</template>
<style scoped>
.page-load {
  min-height: 22rem;
  padding-block: 1rem;
}
.page-load--compact {
  min-height: 3rem;
  padding-block: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.page-load--compact.page-load--pending {
  min-height: 0;
  height: 0;
  padding-block: 0;
  overflow: hidden;
}
</style>
