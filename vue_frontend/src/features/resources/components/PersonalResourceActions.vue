<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
defineProps({ state: { type: Object, required: true } })
const emit = defineEmits(['change'])
</script>
<template>
  <div class="grid grid-cols-3 gap-3 w-full">
    <AppButton
      class="w-full h-12 p-0 min-w-0"
      :aria-pressed="state.isFavorite"
      :variant="state.isFavorite ? 'primary' : 'neutral'"
      aria-label="收藏"
      :disabled="!!state.busy"
      :loading="state.busy === 'favorite'"
      :title="state.isFavorite ? '取消收藏' : '添加到收藏'"
      @click="emit('change', { is_favorite: !state.isFavorite }, 'favorite')"
    >
      <svg
        class="w-5 h-5"
        :fill="state.isFavorite ? 'currentColor' : 'none'"
        stroke="currentColor"
        stroke-width="1.8"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>
    </AppButton>
    <AppButton
      class="w-full h-12 p-0 min-w-0"
      :aria-pressed="state.watched"
      :variant="state.watched ? 'primary' : 'neutral'"
      aria-label="已观看"
      :disabled="!!state.busy"
      :loading="state.busy === 'watched'"
      :title="state.watched ? '标记为未观看' : '标记为已观看'"
      @click="emit('change', { watched: !state.watched }, 'watched')"
    >
      <svg
        class="w-5 h-5"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path d="M2 12s4-8 10-8 10 8 10 8-4 8-10 8S2 12 2 12Z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    </AppButton>
    <AppButton
      class="w-full h-12 p-0 min-w-0"
      :aria-pressed="state.watchLater"
      :variant="state.watchLater ? 'primary' : 'neutral'"
      aria-label="稍后再看"
      :title="state.watchLater ? '移出稍后再看' : '加入稍后再看'"
      :disabled="!!state.busy"
      :loading="state.busy === 'later'"
      @click="emit('change', { watch_later: !state.watchLater }, 'later')"
    >
      <svg
        class="w-5 h-5"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    </AppButton>
  </div>
</template>
