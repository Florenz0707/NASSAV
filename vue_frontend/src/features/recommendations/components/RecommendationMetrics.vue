<script setup>
defineProps({ cards: { type: Array, required: true }, loading: Boolean })
defineEmits(['refresh'])
</script>
<template>
  <section class="metrics-panel">
    <div v-for="card in cards" :key="card.key" class="metrics-card">
      <span class="metrics-label">{{ card.label }}</span>
      <span class="metrics-value">{{ loading ? '...' : card.value }}</span>
    </div>
    <button
      class="metrics-refresh-btn"
      type="button"
      :disabled="loading"
      aria-label="刷新推荐指标"
      @click="$emit('refresh')"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M4 4v6h6M20 20v-6h-6M5.64 18.36A9 9 0 0 0 18.36 5.64M18.36 5.64H14M5.64 18.36H10"
        ></path>
      </svg>
    </button>
  </section>
</template>
