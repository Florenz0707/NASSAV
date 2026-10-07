<script setup>
import { computed, ref, useAttrs, useId } from 'vue'
import AppIcon from './AppIcon.vue'
defineOptions({ inheritAttrs: false })
const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  id: { type: String, default: '' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  error: { type: String, default: '' },
  multiline: Boolean,
  disabled: Boolean,
  clearable: { type: Boolean, default: true },
  type: { type: String, default: 'text' },
})
const emit = defineEmits(['update:modelValue', 'clear'])
const attrs = useAttrs(),
  control = ref(null),
  generatedId = useId()
const inputId = computed(() => props.id || generatedId)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(
  () =>
    [attrs['aria-describedby'], props.error ? errorId.value : ''].filter(Boolean).join(' ') ||
    undefined
)
function controlAttrs() {
  const forwarded = { ...attrs }
  delete forwarded.class
  delete forwarded.style
  return forwarded
}
function clear() {
  emit('update:modelValue', '')
  emit('clear')
  control.value?.focus()
}
</script>
<template>
  <div class="ui-field" :class="attrs.class" :style="attrs.style">
    <label v-if="label" :for="inputId" class="ui-field__label">{{ label }}</label>
    <div class="ui-field__control" :class="{ 'ui-field__control--icon': $slots.icon }">
      <span v-if="$slots.icon" class="ui-field__icon" aria-hidden="true"><slot name="icon" /></span>
      <component
        :is="multiline ? 'textarea' : 'input'"
        ref="control"
        v-bind="controlAttrs()"
        :id="inputId"
        :type="multiline ? undefined : type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
        :aria-label="attrs['aria-label'] || undefined"
        class="ui-input"
        :class="{ 'ui-input--error': error, 'ui-input--clearable': clearable }"
        @input="emit('update:modelValue', $event.target.value)"
      />
      <button
        v-if="clearable && String(modelValue).length && !disabled"
        type="button"
        class="ui-field__clear"
        :aria-label="`清空${label || attrs['aria-label'] || '输入'}`"
        @click="clear"
      >
        <AppIcon name="close" class="w-4 h-4" />
      </button>
    </div>
    <p v-if="error" :id="errorId" class="ui-field__error" role="alert">{{ error }}</p>
  </div>
</template>
<style scoped>
@layer components {
  .ui-field {
    min-width: 0;
  }
  .ui-field__label {
    display: block;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  .ui-field__control {
    position: relative;
  }
  .ui-input {
    display: block;
    width: 100%;
    min-height: 46px;
    padding: 0.75rem 1rem;
    border: 1px solid var(--border-color);
    border-radius: 0.625rem;
    background: var(--bg-input);
    color: var(--text-primary);
    caret-color: var(--accent-primary-text);
    transition:
      border-color 0.15s,
      box-shadow 0.15s;
  }
  textarea.ui-input {
    resize: vertical;
    line-height: 1.6;
  }
  .ui-input--clearable {
    padding-right: 3rem;
  }
  .ui-input::placeholder {
    color: var(--text-muted);
    opacity: 1;
  }
  .ui-input:focus {
    outline: none;
    border-color: var(--accent-primary);
    box-shadow: 0 0 0 3px var(--focus-ring);
  }
  .ui-input--error {
    border-color: var(--accent-danger);
  }
  .ui-input--error:focus {
    border-color: var(--accent-danger);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-danger) 20%, transparent);
  }
  .ui-input:disabled {
    background: var(--disabled-surface);
    color: var(--text-muted);
    cursor: not-allowed;
  }
  .ui-field__icon {
    position: absolute;
    top: 50%;
    left: 1rem;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
  }
  .ui-field__control--icon .ui-input {
    padding-left: 3rem;
  }
  .ui-field__clear {
    position: absolute;
    right: 0.75rem;
    top: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    color: var(--text-secondary);
    background: var(--surface-raised);
  }
  .ui-field__clear:hover {
    background: var(--neutral-pressed);
  }
  .ui-field__clear:focus-visible {
    outline: 3px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .ui-field__error {
    margin-top: 0.5rem;
    color: var(--accent-danger);
    font-size: 0.875rem;
  }
  .ui-input::-webkit-search-cancel-button {
    appearance: none;
  }
  @media (prefers-reduced-motion: reduce) {
    .ui-input {
      transition: none;
    }
  }
}
</style>
