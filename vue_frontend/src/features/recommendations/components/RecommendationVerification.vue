<script setup>
import { computed } from 'vue'

const props = defineProps({ statistics: { type: Object, required: true } })
const counts = computed(() => [
  { label: '详情获取成功', value: props.statistics.detail_success_count },
  { label: '黑名单排除', value: props.statistics.blacklist_excluded_count },
  {
    label: '未核验',
    value: props.statistics.unverified_count ?? props.statistics.excluded_unverified_count,
  },
  { label: '合格候选', value: props.statistics.qualified_count ?? props.statistics.verified_count },
])
</script>

<template>
  <section aria-label="推荐核验统计" role="status" class="space-y-3">
    <h3 class="text-base font-semibold text-primary">本轮核验</h3>
    <dl class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div v-for="item in counts" :key="item.label">
        <dt class="text-secondary text-sm">{{ item.label }}</dt>
        <dd class="text-primary font-semibold">{{ item.value ?? '—' }}</dd>
      </div>
    </dl>
    <p class="text-muted text-sm mt-3">
      <template v-if="statistics.detail_attempt_count != null">
        已尝试 {{ statistics.detail_attempt_count }} 个详情。
      </template>
      未核验不代表失败；合格候选经排序后，可能只返回其中一部分。
    </p>
  </section>
</template>
