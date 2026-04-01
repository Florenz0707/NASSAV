<script setup>
defineProps({
  hasCookie: {
    type: Boolean,
    required: true,
  },
})
</script>

<template>
  <span
    v-if="hasCookie"
    class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-sm"
  >
    <span>✓</span>
    <span>已设置</span>
  </span>
  <span
    v-else
    class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 text-red-400 text-sm"
  >
    <span>✗</span>
    <span>未设置</span>
  </span>
</template>
