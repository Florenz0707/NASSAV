<script setup>
defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '搜索...' },
})
const emit = defineEmits(['update:modelValue'])
</script>
<template>
  <div class="relative flex-1 min-w-0">
    <svg
      class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
      />
    </svg>
    <input
      :value="modelValue"
      :placeholder="placeholder"
      :aria-label="placeholder"
      type="search"
      class="search-input w-full py-3 px-4 pl-12 border rounded-lg text-primary transition-colors duration-200"
      @input="emit('update:modelValue', $event.target.value)"
    />
  </div>
</template>
<style scoped>
.search-input {
  background: var(--bg-input);
  border-color: var(--border-color);
}
.search-input::placeholder {
  color: var(--text-muted);
}
.search-input:focus-visible {
  border-color: var(--accent-primary);
}
</style>
