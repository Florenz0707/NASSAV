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
    class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent-success/10 text-accent-success text-[0.85rem] font-medium"
  >
    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M5 13l4 4L19 7"
      ></path>
    </svg>
    <span>已设置</span>
  </span>
  <span
    v-else
    class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-accent-danger/10 text-accent-danger text-[0.85rem] font-medium"
  >
    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M6 18L18 6M6 6l12 12"
      ></path>
    </svg>
    <span>未设置</span>
  </span>
</template>
