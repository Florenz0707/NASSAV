<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
defineProps({ cards: { type: Array, required: true }, loading: Boolean, resetDisabled: Boolean })
defineEmits(['refresh', 'resetHistory'])
</script>
<template>
  <section aria-label="推荐历史信息">
    <header class="flex items-center justify-between gap-3 mb-3">
      <h3 class="text-base font-semibold text-primary">历史信息</h3>
      <div class="ml-auto flex items-center justify-end flex-wrap gap-2">
        <AppButton
          variant="neutral"
          size="sm"
          :loading="loading"
          aria-label="刷新推荐指标"
          @click="$emit('refresh')"
        >
          <svg
            class="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v6h6M20 20v-6h-6M5.64 18.36A9 9 0 0 0 18.36 5.64M18.36 5.64H14M5.64 18.36H10"
            />
          </svg>
          刷新
        </AppButton>
        <AppButton
          variant="danger"
          size="sm"
          :disabled="loading || resetDisabled"
          @click="$emit('resetHistory')"
          >重置历史
        </AppButton>
      </div>
    </header>
    <dl class="grid grid-cols-2 sm:grid-cols-3 gap-3">
      <div v-for="card in cards" :key="card.key" class="bg-primary rounded-xl p-3 min-w-0">
        <dt class="text-secondary text-sm break-words">{{ card.label }}</dt>
        <dd class="text-primary text-xl font-semibold mt-1 break-words">
          {{ loading ? '…' : card.value }}
        </dd>
      </div>
    </dl>
  </section>
</template>
