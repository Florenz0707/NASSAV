<script setup>
import RecommendationVerification from './RecommendationVerification.vue'
import RecommendationSeeds from './RecommendationSeeds.vue'
defineProps({
  statistics: { type: Object, default: null },
  groups: { type: Object, required: true },
  elapsedSeconds: { type: Number, default: null },
})
</script>
<template>
  <div
    v-if="statistics || groups.actor.length || groups.genre.length"
    class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4"
  >
    <details v-if="statistics" class="bg-secondary rounded-xl p-3 min-w-0">
      <summary class="cursor-pointer text-sm text-primary">
        <strong>本轮核验</strong>
        <span class="text-muted ml-2"
          >已通过 {{ statistics.verified_count ?? statistics.qualified_count ?? '—' }} /
          {{ statistics.recalled_count ?? statistics.candidate_count ?? '—' }} 条，总用时
          {{ elapsedSeconds ?? '—' }} 秒</span
        >
      </summary>
      <div class="mt-3"><RecommendationVerification :statistics="statistics" /></div>
    </details>
    <details
      v-if="groups.actor.length || groups.genre.length"
      class="bg-secondary rounded-xl p-3 min-w-0"
    >
      <summary class="cursor-pointer text-sm text-primary">
        <strong>推荐依据</strong>
        <span class="text-muted ml-2"
          >演员 {{ groups.actor.length }} · 类别 {{ groups.genre.length }}</span
        >
      </summary>
      <div class="mt-3"><RecommendationSeeds :groups="groups" /></div>
    </details>
  </div>
</template>
