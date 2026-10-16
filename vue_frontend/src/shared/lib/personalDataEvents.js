// Payload-free invalidation: topics describe data domains, never user values.
const listeners = new Set()
export function onPersonalDataChanged(listener, topics = null) {
  const receive = (event) => {
    if (!topics || !event.topics || topics.some((topic) => event.topics.includes(topic)))
      listener(event)
  }
  listeners.add(receive)
  return () => listeners.delete(receive)
}
export function personalDataChanged(response, topics = null) {
  for (const listener of listeners) listener({ topics })
  return response
}
