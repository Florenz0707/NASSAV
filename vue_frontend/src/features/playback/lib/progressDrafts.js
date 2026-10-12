const key = 'nassav-playback-drafts-v1'
const ttl = 7 * 86400000
function safeStorage() {
  try {
    return globalThis.localStorage
  } catch {
    return null
  }
}
function read(storage) {
  try {
    const value = JSON.parse(storage?.getItem(key) || '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch {
    return {}
  }
}
export function clearPlaybackDrafts(storage = safeStorage()) {
  try {
    storage?.removeItem(key)
  } catch {
    /* Storage is optional. */
  }
}
export function createProgressDrafts(storage = safeStorage(), now = () => Date.now()) {
  function write(rows) {
    try {
      storage?.setItem(key, JSON.stringify(rows))
    } catch {
      /* Database remains authoritative. */
    }
  }
  return {
    get(snapshot) {
      const value = read(storage)[snapshot.ledger_key]
      if (
        !value ||
        !Number.isFinite(value.saved_at) ||
        now() - value.saved_at > ttl ||
        value.base_version !== snapshot.version ||
        value.writer_generation !== snapshot.writer_generation
      )
        return null
      if (
        !Number.isFinite(value.position_seconds) ||
        !Number.isFinite(value.duration_seconds) ||
        value.position_seconds < 0 ||
        value.position_seconds > value.duration_seconds ||
        value.duration_seconds <= 0 ||
        value.duration_seconds > 604800
      )
        return null
      return {
        ...snapshot,
        position_seconds: value.position_seconds,
        duration_seconds: value.duration_seconds,
        completed: value.completed === true,
      }
    },
    put(snapshot, body) {
      if (!snapshot?.ledger_key) return
      const rows = Object.entries(read(storage))
        .filter(
          ([, value]) => value && Number.isFinite(value.saved_at) && now() - value.saved_at <= ttl
        )
        .sort((a, b) => b[1].saved_at - a[1].saved_at)
        .slice(0, 19)
      write({
        ...Object.fromEntries(rows),
        [snapshot.ledger_key]: {
          position_seconds: body.position_seconds,
          duration_seconds: body.duration_seconds,
          completed: body.completed,
          writer_generation: body.writer_generation,
          sequence: body.sequence,
          base_version: body.expected_version,
          saved_at: now(),
        },
      })
    },
    remove(snapshot, body) {
      const rows = read(storage),
        value = rows[snapshot?.ledger_key]
      if (value?.writer_generation === body.writer_generation && value.sequence <= body.sequence) {
        delete rows[snapshot.ledger_key]
        write(rows)
      }
    },
  }
}
