import { nextTick, onBeforeUnmount, watch } from 'vue'

const dialogs = []
let originalOverflow = ''
let nextId = 0
const focusableSelector =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

export function useDialog(visible, root, close) {
  const titleId = `dialog-title-${++nextId}`
  let active = false
  let previousFocus = null
  const entry = { root }

  function keydown(event) {
    if (dialogs.at(-1) !== entry) return
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      close()
    }
    if (event.key === 'Tab') {
      const targets = [...(root.value?.querySelectorAll(focusableSelector) || [])].filter(
        (el) => el.getClientRects().length
      )
      const first = targets[0],
        last = targets.at(-1)
      if (!first) {
        event.preventDefault()
        root.value?.focus()
        return
      }
      if (
        event.shiftKey &&
        (document.activeElement === first || !root.value?.contains(document.activeElement))
      ) {
        event.preventDefault()
        last.focus()
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !root.value?.contains(document.activeElement))
      ) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  function release() {
    if (!active) return
    active = false
    const index = dialogs.indexOf(entry)
    const wasTop = index === dialogs.length - 1
    dialogs.splice(index, 1)
    document.removeEventListener('keydown', keydown, true)
    if (!dialogs.length) document.body.style.overflow = originalOverflow
    if (wasTop && previousFocus?.isConnected) previousFocus.focus()
  }

  watch(
    visible,
    async (show) => {
      if (!show) {
        release()
        return
      }
      if (active) return
      active = true
      previousFocus = document.activeElement
      if (!dialogs.length) {
        originalOverflow = document.body.style.overflow
        document.body.style.overflow = 'hidden'
      }
      dialogs.push(entry)
      document.addEventListener('keydown', keydown, true)
      await nextTick()
      if (active) (root.value?.querySelector(focusableSelector) || root.value)?.focus()
    },
    { immediate: true }
  )
  onBeforeUnmount(release)
  return { titleId, descriptionId: `${titleId}-description` }
}
