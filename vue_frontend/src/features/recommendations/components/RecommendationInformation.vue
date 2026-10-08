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
      @refresh="$emit('refreshMetrics')"
      @reset="$emit('resetHistory')"
    />
  </div>
</template>
