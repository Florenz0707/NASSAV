<script setup>
import RecommendationMetrics from './RecommendationMetrics.vue'
defineProps({ cards: { type: Array, required: true }, metricsLoading: Boolean, loading: Boolean })
defineEmits(['refreshMetrics', 'resetHistory'])
</script>
<template>
  <div class="space-y-4 recommendation-information">
    <RecommendationMetrics
      :cards="cards"
      :loading="metricsLoading"
      :reset-disabled="loading"
      @refresh="$emit('refreshMetrics')"
      @reset-history="$emit('resetHistory')"
    />
  </div>
</template>
