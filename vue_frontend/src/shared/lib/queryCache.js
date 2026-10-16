// Memory only. Owners clear the cache on identity or relevant data changes.
const copy = (value) => (value === undefined ? value : JSON.parse(JSON.stringify(value)))
export function createQueryCache({ ttl = 30000, limit = 20, now = () => Date.now() } = {}) {
  const entries = new Map(),
    pending = new Map()
  let epoch = 0
  function peek(key) {
    const hit = entries.get(key)
    if (!hit) return null
    entries.delete(key)
    entries.set(key, hit)
    return { value: copy(hit.value), fresh: now() - hit.time < ttl }
  }
  function clear() {
    epoch++
    entries.clear()
    pending.clear()
  }
  async function read(key, load, { force = false } = {}) {
    const hit = peek(key)
    if (!force && hit?.fresh) return hit.value
    if (!force && pending.has(key)) return copy(await pending.get(key))
    const current = epoch
    // Invoke synchronously, preserving consumers' request ordering.
    const request = Promise.resolve(load())
      .then((value) => {
        if (epoch !== current || pending.get(key) !== request) return null
        entries.delete(key)
        entries.set(key, { value: copy(value), time: now() })
        while (entries.size > limit) entries.delete(entries.keys().next().value)
        return value
      })
      .finally(() => {
        if (pending.get(key) === request) pending.delete(key)
      })
    pending.set(key, request)
    return copy(await request)
  }
  return { read, peek, clear }
}
