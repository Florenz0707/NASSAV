<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
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
    />
    <div class="flex justify-end border-t border-[var(--border-color)] pt-4">
      <AppButton
        variant="danger"
        size="sm"
        :disabled="loading || metricsLoading"
        @click="$emit('resetHistory')"
        >重置历史</AppButton
      >
    </div>
  </div>
</template>
