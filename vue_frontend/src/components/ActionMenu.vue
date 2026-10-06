<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount, useId, watch } from 'vue'
import AppButton from './AppButton.vue'
const props = defineProps({
  label: { type: String, required: true },
  options: { type: Array, required: true },
  disabled: Boolean,
  danger: Boolean,
  align: { type: String, default: 'left' },
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
      :variant="danger ? 'danger' : 'neutral'"
      :disabled="disabled"
      :aria-label="label"
      aria-haspopup="menu"
      :aria-expanded="open"
      :aria-controls="menuId"
      @click="toggle"
    >
      {{ label }}
    </AppButton>
    <div
      v-if="open"
      :id="menuId"
      role="menu"
      :aria-label="label"
      class="absolute z-[80] min-w-[120px] max-h-[50vh] overflow-y-auto rounded-lg bg-secondary border shadow-lg"
      :class="[
        below ? 'top-full mt-2' : 'bottom-full mb-2',
        align === 'right' ? 'right-0' : 'left-0',
      ]"
    >
      <button
        v-for="option in options"
        :key="option.action || option.text"
        type="button"
        role="menuitem"
        :disabled="option.disabled"
        class="block w-full px-4 py-2.5 text-left text-sm hover:bg-surface-subtle/10 focus-visible:bg-surface-subtle/10 disabled:opacity-50"
        :class="danger ? 'text-accent-danger' : 'text-primary'"
        @click="select(option)"
      >
        {{ option.text }}
      </button>
    </div>
  </div>
</template>
