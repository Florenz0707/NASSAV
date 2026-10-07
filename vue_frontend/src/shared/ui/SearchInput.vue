<script setup>
import AppInput from './AppInput.vue'
defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '搜索编号、标题或演员' },
  error: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
</script>
<template>
  <AppInput
    class="flex-1 min-w-0"
    type="search"
    :model-value="modelValue"
    :placeholder="placeholder"
    :aria-label="placeholder"
    :error="error"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #icon
      ><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        /></svg
    ></template>
  </AppInput>
</template>
