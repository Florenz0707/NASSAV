<template>
  <div class="mb-4 flex flex-wrap items-center gap-2">
    <div>
      <AppButton variant="neutral" class="h-10 rounded-md" @click="$emit('toggle-batch-mode')">
        {{ batchMode ? '退出批量' : '批量操作' }}
      </AppButton>
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
      <AppButton
        variant="neutral"
        class="h-10 rounded-md"
        :disabled="batchLoading"
        :loading="batchLoading && busyAction === 'refresh'"
        @click="$emit('batch-refresh')"
        >批量刷新</AppButton
      >
      <AppButton
        tone="coral"
        class="h-10 rounded-md"
        :disabled="batchLoading"
        :loading="batchLoading && busyAction === 'download'"
        @click="$emit('batch-download')"
        >批量下载</AppButton
      >
      <AppButton
        variant="danger"
        class="h-10 rounded-md"
        :disabled="batchLoading"
        :loading="batchLoading && busyAction === 'delete'"
        @click="$emit('batch-delete')"
        >{{ deleteLabel }}</AppButton
      >
    </div>
  </div>
</template>

<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
import AppCheckbox from '../../../shared/ui/AppCheckbox.vue'
defineProps({
  busyAction: { type: String, default: '' },
  deleteLabel: { type: String, default: '批量删除' },
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
