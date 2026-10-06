<script setup>
import AppCheckbox from './AppCheckbox.vue'
defineProps({ checked: Boolean, indeterminate: Boolean, label: { type: String, required: true } })
defineEmits(['change'])
</script>
<template>
  <AppCheckbox
    :checked="checked"
    :indeterminate="indeterminate"
    :label="label"
    @change="$emit('change', $event)"
  />
</template>
