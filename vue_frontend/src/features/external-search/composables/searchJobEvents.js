const listeners = new Set()

export function subscribeSearchJobUpdates(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function notifySearchJobUpdate(event) {
  for (const listener of listeners) listener(event)
}
