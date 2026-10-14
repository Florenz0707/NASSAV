// Dirty-close decisions and pending navigation share one explicit discard prompt.
export function createNoteDialog({ state, ui, save }) {
  let pending = null,
    generation = 0
  const dirty = () => state.notes !== state.savedNotes
  function settle(value) {
    pending?.resolve(value)
    pending = null
    ui.confirm = false
  }
  function reset() {
    generation++
    settle(false)
    ui.open = false
  }
  function open() {
    if (state.busy) return
    state.notes = state.savedNotes
    state.error = ''
    ui.open = true
  }
  function close() {
    if (!ui.open) return Promise.resolve(true)
    if (state.busy) return Promise.resolve(false)
    if (!dirty()) {
      settle(true)
      ui.open = false
      return Promise.resolve(true)
    }
    if (!pending) {
      let resolve
      const promise = new Promise((yes) => {
        resolve = yes
      })
      pending = { promise, resolve }
      ui.confirm = true
    }
    return pending.promise
  }
  function discard() {
    state.notes = state.savedNotes
    ui.open = false
    settle(true)
  }
  function keep() {
    settle(false)
  }
  async function persist() {
    const ticket = generation
    const result = await save({ notes: state.notes }, 'notes')
    if (ticket === generation && result.success && !dirty()) ui.open = false
    return result
  }
  return { open, close, discard, keep, reset, persist, dirty }
}
