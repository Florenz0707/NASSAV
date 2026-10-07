<script setup>
import LoadingSpinner from './LoadingSpinner.vue'
defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: (value) => ['primary', 'neutral', 'danger'].includes(value),
  },
  tone: { type: String, default: '', validator: (value) => ['', 'warm'].includes(value) },
  size: { type: String, default: 'md', validator: (value) => ['sm', 'md'].includes(value) },
  disabled: Boolean,
  loading: Boolean,
  loadingText: { type: String, default: '' },
})
</script>
<template>
  <button
    type="button"
    class="ui-button"
    :class="[`ui-button--${variant}`, `ui-button--${size}`, tone ? `ui-button--tone-${tone}` : '']"
    :disabled="disabled || loading"
    :aria-busy="loading"
    :aria-label="loading ? loadingText || '正在处理' : undefined"
  >
    <span class="ui-button__content" :class="{ 'ui-button__content--hidden': loading }"
      ><slot
    /></span>
    <span v-if="loading" class="ui-button__busy" aria-hidden="true"
      ><LoadingSpinner size="small" /><span v-if="loadingText">{{ loadingText }}</span></span
    >
  </button>
</template>
<style scoped>
@layer components {
  .ui-button {
    position: relative;
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
      background-color 0.15s,
      border-color 0.15s,
      transform 0.1s;
  }
  .ui-button__content {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: inherit;
  }
  .ui-button__content--hidden {
    visibility: hidden;
  }
  .ui-button__busy {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  .ui-button__busy :deep(.loading-indicator) {
    color: inherit;
  }
  .ui-button--sm {
    padding: 0.375rem 0.75rem;
    font-size: 0.85rem;
  }
  .ui-button--tone-warm {
    --button-fill: var(--warm-fill);
    --button-fill-hover: var(--warm-fill-hover);
    --button-fill-pressed: var(--warm-fill-pressed);
    --button-surface: var(--warm-surface);
    --button-surface-hover: var(--warm-surface-hover);
    --button-surface-pressed: var(--warm-surface-pressed);
    --button-ink: var(--warm-text);
  }
  .ui-button--tone-warm.ui-button--neutral {
    border-color: color-mix(in srgb, var(--warm-text) 25%, transparent);
  }
  .ui-button--tone-warm:focus-visible {
    outline-color: color-mix(in srgb, var(--warm-text) 35%, transparent);
  }
  .ui-button--primary {
    background: var(--button-fill, var(--accent-primary));
    color: var(--on-accent);
  }
  .ui-button--primary:hover:not(:disabled) {
    background: var(--button-fill-hover, var(--accent-primary-hover));
    box-shadow: var(--button-shadow);
  }
  .ui-button--primary:active:not(:disabled) {
    background: var(--button-fill-pressed, var(--accent-primary-pressed));
  }
  .ui-button--neutral {
    background: var(--button-surface, var(--bg-secondary));
    color: var(--button-ink, var(--text-primary));
    border-color: var(--border-color);
  }
  .ui-button--neutral:hover:not(:disabled) {
    background: var(--button-surface-hover, var(--neutral-hover));
  }
  .ui-button--neutral:active:not(:disabled) {
    background: var(--button-surface-pressed, var(--neutral-pressed));
  }
  .ui-button--danger {
    background: var(--danger-surface);
    color: var(--accent-danger);
    border-color: color-mix(in srgb, var(--accent-danger) 25%, transparent);
  }
  .ui-button--danger:hover:not(:disabled) {
    background: var(--danger-hover);
  }
  .ui-button--danger:active:not(:disabled) {
    background: var(--danger-pressed);
  }
  .ui-button:active:not(:disabled) {
    transform: translateY(1px);
  }
  .ui-button:focus-visible {
    outline: 3px solid var(--focus-ring);
    outline-offset: 3px;
  }
  .ui-button--danger:focus-visible {
    outline-color: color-mix(in srgb, var(--accent-danger) 25%, transparent);
  }
  .ui-button:disabled:not([aria-busy='true']) {
    background: var(--disabled-surface);
    color: var(--text-muted);
    border-color: var(--border-color);
    cursor: not-allowed;
    box-shadow: none;
  }
  .ui-button[aria-busy='true'] {
    cursor: wait;
  }
  @media (prefers-reduced-motion: reduce) {
    .ui-button {
      transition: none;
    }
    .ui-button:active {
      transform: none;
    }
  }
}
</style>
