<script setup>
import AppButton from '../../../shared/ui/AppButton.vue'
defineProps({ adding: Boolean, added: Boolean })
defineEmits(['add', 'open', 'view'])
</script>
<template>
  <div class="grid grid-cols-[minmax(0,1fr)_auto] gap-2 mt-auto remote-resource-actions">
    <AppButton
      :variant="added ? 'neutral' : 'primary'"
      tone="warm"
      :disabled="added"
      :loading="adding"
      loading-text="添加中"
      @click="$emit('add')"
      >{{ added ? '已添加' : '加入资源库' }}</AppButton
    >
    <AppButton variant="neutral" @click="added ? $emit('view') : $emit('open')">{{
      added ? '查看详情' : '跳转来源'
    }}</AppButton>
  </div>
</template>
