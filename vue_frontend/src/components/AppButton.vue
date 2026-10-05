<script setup>
import LoadingSpinner from './LoadingSpinner.vue'
defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: (value) => ['primary', 'neutral', 'danger'].includes(value),
  },
  size: { type: String, default: 'md', validator: (value) => ['sm', 'md'].includes(value) },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})
</script>
<template>
  <button
    type="button"
    class="ui-button"
    :class="[`ui-button--${variant}`, `ui-button--${size}`]"
    :disabled="disabled || loading"
    :aria-busy="loading"
  >
    <LoadingSpinner v-if="loading" size="small" aria-hidden="true" />
    <slot />
  </button>
</template>
<style scoped>
@layer components {
  .ui-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border: 1px solid transparent;
    border-radius: 0.75rem;
    font: inherit;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition:
      background-color 0.2s,
      filter 0.2s;
  }
  .ui-button:hover:not(:disabled) {
    filter: brightness(1.08);
  }
  .ui-button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .ui-button--sm {
    padding: 0.375rem 0.75rem;
    font-size: 0.85rem;
  }
  .ui-button--primary {
    background: var(--accent-primary);
    color: var(--on-accent);
  }
  .ui-button--danger {
    background: var(--accent-danger);
    color: var(--text-inverse);
  }
  .ui-button--neutral {
    background: var(--bg-secondary);
    color: var(--text-primary);
    border-color: var(--border-color);
  }
  .ui-button--neutral:hover:not(:disabled) {
    background: var(--bg-white-8);
  }
}
</style>
