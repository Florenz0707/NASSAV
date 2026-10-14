// Payload-free invalidation: never broadcasts user data or credentials.
const listeners = new Set()
export function onPersonalDataChanged(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
export function personalDataChanged(response) {
  for (const listener of listeners) listener()
  return response
}
