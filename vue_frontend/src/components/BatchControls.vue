<template>
  <div class="mb-4 flex flex-wrap items-center gap-2">
    <div>
      <button
        class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md bg-surface-subtle/[0.06] hover:bg-[var(--bg-white-10)] transition-colors duration-200"
        style="color: var(--text-primary)"
        @click="$emit('toggle-batch-mode')"
      >
        <span class="text-sm">{{ batchMode ? '退出批量' : '批量操作' }}</span>
      </button>
    </div>

    <div v-if="batchMode" class="flex items-center gap-2 flex-wrap">
      <div class="inline-flex items-center gap-3 text-sm" style="color: var(--text-secondary)">
        <AppCheckbox
          :checked="selectedCount === totalCount && totalCount > 0"
          :indeterminate="selectedCount > 0 && selectedCount < totalCount"
          label="选择当前列表全部资源"
          @change="$emit('toggle-select-all', $event)"
        />
        <span>已选择 {{ selectedCount }} 项</span>
      </div>
      <button
        class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md bg-surface-subtle/[0.06] text-sm hover:bg-[var(--bg-white-10)] disabled:opacity-60 transition-colors duration-200"
        style="color: var(--text-primary)"
        :disabled="batchLoading"
        @click="$emit('batch-refresh')"
      >
        批量刷新
      </button>
      <button
        class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md text-white shadow text-sm hover:brightness-105 disabled:opacity-60 transition-all duration-200"
        style="background: linear-gradient(135deg, var(--accent-primary), var(--accent-primary))"
        :disabled="batchLoading"
        @click="$emit('batch-download')"
      >
        批量下载
      </button>
      <button
        class="inline-flex items-center justify-center px-3 py-2 h-10 rounded-md text-white shadow text-sm hover:brightness-95 disabled:opacity-60 transition-all duration-200"
        style="background: var(--accent-danger)"
        :disabled="batchLoading"
        @click="$emit('batch-delete')"
      >
        批量删除
      </button>
    </div>
  </div>
</template>

<script setup>
import AppCheckbox from './AppCheckbox.vue'
defineProps({
  batchMode: {
    type: Boolean,
    default: false,
  },
  batchLoading: {
    type: Boolean,
    default: false,
  },
  selectedCount: {
    type: Number,
    default: 0,
  },
  totalCount: {
    type: Number,
    default: 0,
  },
})

defineEmits([
  'toggle-batch-mode',
  'toggle-select-all',
  'batch-refresh',
  'batch-download',
  'batch-delete',
])
</script>
