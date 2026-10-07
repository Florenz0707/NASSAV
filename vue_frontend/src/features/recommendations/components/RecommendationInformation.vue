<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
import RecommendationMetrics from './RecommendationMetrics.vue'
import RecommendationVerification from './RecommendationVerification.vue'
import RecommendationSeeds from './RecommendationSeeds.vue'
defineProps({
  cards: { type: Array, required: true },
  metricsLoading: Boolean,
  loading: Boolean,
  statistics: { type: Object, default: null },
  groups: { type: Object, required: true },
})
defineEmits(['refreshMetrics', 'refreshExternal', 'clear', 'resetHistory'])
</script>
<template>
  <div class="space-y-5 recommendation-information">
    <RecommendationMetrics
      :cards="cards"
      :loading="metricsLoading"
      @refresh="$emit('refreshMetrics')"
    />
    <div class="border-t border-[var(--border-color)] pt-5">
      <RecommendationVerification v-if="statistics" :statistics="statistics" />
      <section v-else aria-label="推荐核验统计">
        <h3 class="text-base font-semibold text-primary">本轮核验</h3>
        <p class="text-muted text-sm mt-2">开始推荐后显示本轮核验信息。</p>
      </section>
    </div>
    <div class="border-t border-[var(--border-color)] pt-5">
      <RecommendationSeeds :groups="groups" />
    </div>
    <section class="border-t border-[var(--border-color)] pt-5">
      <h3 class="text-base font-semibold text-primary mb-3">管理操作</h3>
      <div class="flex flex-wrap gap-2">
        <AppButton variant="neutral" size="sm" :disabled="loading" @click="$emit('refreshExternal')"
          >刷新外部结果</AppButton
        >
        <AppButton variant="neutral" size="sm" :disabled="loading" @click="$emit('clear')"
          >清空页面</AppButton
        >
        <AppButton
          variant="danger"
          size="sm"
          :disabled="loading || metricsLoading"
          @click="$emit('resetHistory')"
          >重置历史</AppButton
        >
      </div>
    </section>
  </div>
</template>
