<script setup>
defineProps({
  hasCookie: {
    type: Boolean,
    required: true,
  },
  verifiedDirectReuse: { type: Boolean, default: false },
  sessionExpired: { type: Boolean, default: false },
})
</script>

<template>
  <span
    v-if="hasCookie"
    class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[0.85rem] font-medium"
    :class="
      sessionExpired
        ? 'bg-accent-danger/10 text-accent-danger'
        : 'bg-accent-success/10 text-accent-success'
    "
  >
    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M5 13l4 4L19 7"
      ></path>
    </svg>
    <span>{{
      verifiedDirectReuse ? '已验证可直连' : sessionExpired ? '已保存 · 会话已过期' : '已保存'
    }}</span>
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
