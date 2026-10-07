<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount, useId, watch } from 'vue'
import AppButton from './AppButton.vue'
const props = defineProps({
  label: { type: String, required: true },
  options: { type: Array, required: true },
  disabled: Boolean,
  danger: Boolean,
  align: { type: String, default: 'left' },
  triggerClass: { type: String, default: '' },
  compact: Boolean,
  buttonText: { type: String, default: '' },
})
const emit = defineEmits(['select'])
const root = ref(null),
  trigger = ref(null),
  open = ref(false),
  below = ref(false)
const menuId = useId()
function close(focus = false) {
  open.value = false
  if (focus) trigger.value?.$el.focus()
}
function outside(event) {
  if (!root.value?.contains(event.target)) close()
}
function focusItem(index) {
  const items = root.value?.querySelectorAll('[role="menuitem"]:not(:disabled)') || []
  items[(index + items.length) % items.length]?.focus()
}
async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    below.value = trigger.value.$el.getBoundingClientRect().top < 200
    await nextTick()
    focusItem(0)
  }
}
function keydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    close(true)
  } else if (event.key === 'Tab') close()
  else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    if (!open.value) {
      toggle()
      return
    }
    const items = [...root.value.querySelectorAll('[role="menuitem"]:not(:disabled)')]
    const index = items.indexOf(document.activeElement)
    focusItem(
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? items.length - 1
          : index + (event.key === 'ArrowDown' ? 1 : -1)
    )
  }
}
function select(option) {
  close(true)
  emit('select', option)
}
watch(
  () => props.disabled,
  (value) => {
    if (value) close()
  }
)
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', outside))
</script>
<template>
  <div ref="root" class="relative" @click.stop @keydown="keydown">
    <AppButton
      ref="trigger"
      :class="triggerClass"
      :variant="danger ? 'danger' : 'neutral'"
      :disabled="disabled"
      :aria-label="label"
      aria-haspopup="menu"
      :aria-expanded="open"
      :aria-controls="menuId"
      @click="toggle"
    >
      {{ buttonText || label }}
    </AppButton>
    <div
      v-if="open"
      :id="menuId"
      role="menu"
      :aria-label="label"
      class="absolute tw-card-menu-popover max-h-[50vh] overflow-y-auto"
      :class="[
        below ? 'top-full mt-2' : 'bottom-full mb-2',
        compact ? (danger ? 'min-w-[85px]' : 'min-w-[110px]') : 'min-w-[120px]',
        align === 'right' ? 'right-0' : 'left-0',
      ]"
    >
      <button
        v-for="option in options"
        :key="option.action || option.text"
        type="button"
        role="menuitem"
        :disabled="option.disabled"
        class="block w-full px-4 py-2.5 text-center border-none transition-colors disabled:opacity-50"
        :class="[
          compact && !danger ? 'text-[0.75rem]' : 'text-[0.8rem]',
          danger && compact
            ? 'text-accent-danger bg-accent-danger/20 hover:bg-accent-danger/10 focus-visible:bg-accent-danger/10'
            : 'text-secondary bg-surface-subtle/8 hover:bg-surface-subtle/[0.14] focus-visible:bg-surface-subtle/[0.14] hover:text-primary focus-visible:text-primary',
        ]"
        @click="select(option)"
      >
        {{ option.text }}
      </button>
    </div>
  </div>
</template>
