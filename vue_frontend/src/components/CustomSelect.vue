<script setup>
import { computed, defineOptions, nextTick, onBeforeUnmount, onMounted, ref, useAttrs } from 'vue'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean],
    default: '',
  },
  options: {
    type: Array,
    default: () => [],
  },
  placeholder: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  size: {
    type: String,
    default: 'md',
  },
  fullWidth: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue', 'change'])
const attrs = useAttrs()
const rootRef = ref(null)
const open = ref(false)

const selectedOption = computed(() => {
  return props.options.find((option) => String(option.value) === String(props.modelValue)) || null
})

const displayLabel = computed(() => {
  if (selectedOption.value) return selectedOption.value.label
  return props.placeholder || '请选择'
})

const sizeClass = computed(() => {
  return props.size === 'sm' ? 'custom-select-button--sm' : 'custom-select-button--md'
})

function closeMenu() {
  open.value = false
}

function toggleMenu() {
  if (props.disabled) return
  open.value = !open.value
}

function handleSelect(option) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  emit('change', option.value)
  closeMenu()
}

function handleDocumentClick(event) {
  if (!rootRef.value) return
  if (!rootRef.value.contains(event.target)) {
    closeMenu()
  }
}

async function handleButtonKeydown(event) {
  if (props.disabled) return
  if (event.key === 'Escape') {
    closeMenu()
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    toggleMenu()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    open.value = true
    await nextTick()
    const firstOption = rootRef.value?.querySelector('.custom-select-option:not(.is-disabled)')
    firstOption?.focus()
  }
}

function handleOptionKeydown(event, index) {
  if (event.key === 'Escape') {
    closeMenu()
    rootRef.value?.querySelector('.custom-select-button')?.focus()
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    const options = rootRef.value?.querySelectorAll('.custom-select-option:not(.is-disabled)')
    options?.[Math.min(index + 1, options.length - 1)]?.focus()
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    const options = rootRef.value?.querySelectorAll('.custom-select-option:not(.is-disabled)')
    options?.[Math.max(index - 1, 0)]?.focus()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocumentClick)
})
</script>

<template>
  <div
    ref="rootRef"
    class="custom-select"
    :class="[
      sizeClass,
      { 'is-open': open, 'is-disabled': disabled, 'is-full-width': fullWidth },
      attrs.class,
    ]"
    :style="attrs.style"
  >
    <button
      type="button"
      class="custom-select-button"
      :disabled="disabled"
      :aria-expanded="open"
      @click="toggleMenu"
      @keydown="handleButtonKeydown"
    >
      <span class="custom-select-label" :class="{ 'is-placeholder': !selectedOption }">
        {{ displayLabel }}
      </span>
      <span class="custom-select-chevron" aria-hidden="true">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8">
          <path stroke-linecap="round" stroke-linejoin="round" d="m5 7 5 6 5-6" />
        </svg>
      </span>
    </button>

    <transition name="custom-select-fade">
      <div
        v-if="open"
        class="custom-select-menu bg-secondary border border-[var(--border-white-10)] rounded-lg shadow-lg"
        role="listbox"
      >
        <button
          v-for="(option, index) in options"
          :key="`${option.value}`"
          type="button"
          class="custom-select-option"
          :class="{
            'is-selected': String(option.value) === String(modelValue),
            'is-disabled': option.disabled,
          }"
          :disabled="option.disabled"
          @click="handleSelect(option)"
          @keydown="handleOptionKeydown($event, index)"
        >
          <span class="custom-select-option-label">{{ option.label }}</span>
          <span
            v-if="String(option.value) === String(modelValue)"
            class="custom-select-option-check flex items-center"
            aria-hidden="true"
          >
            <svg class="w-4 h-4 text-accent-tertiary" viewBox="0 0 20 20" fill="currentColor">
              <path
                fill-rule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clip-rule="evenodd"
              />
            </svg>
          </span>
        </button>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.custom-select {
  position: relative;
  display: inline-block;
}

.custom-select.is-full-width {
  width: 100%;
}

.custom-select-button {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.85rem;
  border: 1px solid var(--border-color);
  border-radius: 1rem;
  background: var(--bg-secondary);
  color: var(--text-primary);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 12px 28px rgba(15, 23, 42, 0.08);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease,
    background 0.2s ease;
}

.custom-select-button:hover:not(:disabled) {
  border-color: rgba(255, 107, 107, 0.26);
  transform: translateY(-1px);
}

.custom-select.is-open .custom-select-button,
.custom-select-button:focus-visible {
  outline: none;
  border-color: rgba(255, 107, 107, 0.42);
  box-shadow:
    0 0 0 3px rgba(255, 107, 107, 0.14),
    0 18px 34px rgba(15, 23, 42, 0.14);
}

.custom-select-button:disabled {
  cursor: not-allowed;
  opacity: 0.68;
}

.custom-select-button--md .custom-select-button {
  min-height: 2.8rem;
  padding: 0.72rem 0.92rem 0.72rem 1rem;
  font-size: 0.9rem;
}

.custom-select-button--sm .custom-select-button {
  min-height: 2.45rem;
  padding: 0.58rem 0.82rem 0.58rem 0.92rem;
  font-size: 0.84rem;
}

.custom-select-label {
  flex: 1;
  min-width: 0;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
}

.custom-select-label.is-placeholder {
  color: var(--text-muted);
}

.custom-select-chevron {
  width: 1rem;
  height: 1rem;
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.custom-select.is-open .custom-select-chevron {
  transform: rotate(180deg);
}

.custom-select-menu {
  position: absolute;
  top: calc(100% + 0.55rem);
  left: 0;
  right: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  padding: 0.4rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 1rem;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.4);
}

.custom-select-option {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 2.55rem;
  padding: 0.65rem 0.8rem;
  border: 1px solid transparent;
  border-radius: 0.82rem;
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    transform 0.18s ease,
    color 0.18s ease;
}

.custom-select-option:hover:not(.is-disabled),
.custom-select-option:focus-visible {
  outline: none;
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: white;
  transform: translateY(-1px);
}

.custom-select-option.is-selected {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: white;
}

.custom-select-option.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.custom-select-option-label {
  flex: 1;
  min-width: 0;
  text-align: left;
  font-size: 0.88rem;
  font-weight: 500;
}

.custom-select-option-check {
  color: var(--accent-primary);
  font-size: 0.84rem;
  font-weight: 700;
}

.custom-select-fade-enter-active,
.custom-select-fade-leave-active {
  transition: all 0.18s ease;
}

.custom-select-fade-enter-from,
.custom-select-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
