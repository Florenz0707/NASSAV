<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
defineProps({
  adding: Boolean,
  added: Boolean,
  checking: Boolean,
  statusError: { type: String, default: '' },
  pending: Boolean,
  unavailable: Boolean,
})
defineEmits(['add', 'open', 'view', 'retry'])
</script>
<template>
  <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-2 mt-auto remote-resource-actions">
    <AppButton
      :variant="added ? 'neutral' : 'primary'"
      tone="coral"
      :disabled="(added && !statusError) || checking"
      :loading="adding || checking"
      :loading-text="checking ? '核对中' : '添加中'"
      @click="statusError ? $emit('retry') : $emit('add')"
      >{{
        statusError ? '重试状态' : added ? (pending ? '准备中' : '已添加') : '加入资源库'
      }}</AppButton
    >
    <AppButton
      variant="neutral"
      :disabled="added && unavailable && !pending"
      @click="added ? $emit('view') : $emit('open')"
      >{{
        added ? (pending ? '查看请求' : unavailable ? '暂不可用' : '查看详情') : '跳转来源'
      }}</AppButton
    >
    <p v-if="statusError" role="alert" class="col-span-2 text-muted text-xs">{{ statusError }}</p>
  </div>
</template>
