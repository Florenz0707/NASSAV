export function optionalSessionStorage() {
  try {
    return globalThis.window?.sessionStorage
  } catch {
    return null
  }
}
// Optional presentation cache. Never an authorization source.
export function readSessionCache(storage, key, now = Date.now()) {
  try {
    const row = JSON.parse(storage?.getItem(key) || 'null')
    if (row?.schema === 1 && Number.isFinite(row.expiresAt) && row.expiresAt > now) return row
    storage?.removeItem(key)
  } catch {
    try {
      storage?.removeItem(key)
    } catch {
      /* Storage may be unavailable. */
    }
  }
  return null
}
export function writeSessionCache(
  storage,
  key,
  value,
  {
    prefix = key,
    ttl = 1800000,
    expiresAt = Infinity,
    limit = 20,
    maxBytes = 2 * 1024 * 1024,
    now = Date.now(),
  } = {}
) {
  try {
    const deadline = Math.min(now + ttl, expiresAt)
    if (!(deadline > now)) {
      storage?.removeItem(key)
      return false
    }
    const text = JSON.stringify({ schema: 1, expiresAt: deadline, savedAt: now, value })
    if (text.length * 2 > maxBytes) {
      storage?.removeItem(key)
      return false
    }
    const rows = [],
      keys = []
    for (let index = 0; index < (storage?.length || 0); index++) keys.push(storage.key(index))
    for (const name of keys) {
      if (name?.startsWith(prefix) && name !== key) {
        const row = readSessionCache(storage, name, now)
        if (row)
          rows.push({
            key: name,
            time: row.savedAt,
            size: (storage.getItem(name)?.length || 0) * 2,
          })
      }
    }
    rows.sort((a, b) => a.time - b.time)
    let bytes = rows.reduce((total, row) => total + row.size, 0) + text.length * 2
    while (rows.length && (rows.length >= limit || bytes > maxBytes)) {
      const row = rows.shift()
      storage.removeItem(row.key)
      bytes -= row.size
    }
    storage?.setItem(key, text)
    return Boolean(storage)
  } catch {
    return false
  }
}
export function clearSessionCache(storage, prefix) {
  try {
    for (let index = (storage?.length || 0) - 1; index >= 0; index--) {
      const key = storage.key(index)
      if (key?.startsWith(prefix)) storage.removeItem(key)
    }
  } catch {
    /* Cache cleanup must not break logout. */
  }
}
