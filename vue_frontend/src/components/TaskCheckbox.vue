<script setup>
defineProps({ checked: Boolean, indeterminate: Boolean, label: { type: String, required: true } })
defineEmits(['change'])
</script>
<template>
  <label class="inline-flex w-5 h-5 relative align-middle cursor-pointer">
    <input
      type="checkbox"
      class="peer absolute inset-0 w-5 h-5 opacity-0 cursor-pointer"
      :checked="checked"
      :indeterminate="indeterminate"
      :aria-label="label"
      @change="$emit('change', $event.target.checked)"
    />
    <span
      class="w-5 h-5 rounded-md border flex items-center justify-center text-on-accent peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent-primary"
      :class="
        checked || indeterminate
          ? 'bg-accent-primary border-accent-primary'
          : 'bg-primary border-[var(--border-color)]'
      "
      aria-hidden="true"
    >
      <svg
        v-if="checked || indeterminate"
        class="w-4 h-4"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path v-if="indeterminate" d="M5 10h10" />
        <path v-else d="m4 10 4 4 8-8" />
      </svg>
    </span>
  </label>
</template>
