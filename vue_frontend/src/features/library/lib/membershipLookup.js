import { ref } from 'vue'

const canonical = (value) => (typeof value === 'string' ? value.trim().toUpperCase() : '')

function checkedStatuses(data, requested) {
  if (!Array.isArray(data) || data.length !== requested.length)
    throw new Error('资源库状态响应不完整')
  const expected = new Set(requested),
    result = new Map()
  for (const row of data) {
    if (
      !expected.has(row?.avid) ||
      result.has(row.avid) ||
      typeof row.is_in_my_library !== 'boolean' ||
      typeof row.is_available !== 'boolean'
    )
      throw new Error('资源库状态响应无效')
    if (
      row.is_in_my_library &&
      (typeof row.entry_id !== 'string' ||
        !row.entry_id ||
        !Number.isInteger(row.entry_version) ||
        row.entry_version < 1 ||
        !['active', 'pending'].includes(row.membership_state))
    )
      throw new Error('资源库关系版本无效')
    result.set(row.avid, {
      avid: row.avid,
      is_in_my_library: row.is_in_my_library,
      is_available: row.is_available,
      entry_id: row.is_in_my_library ? row.entry_id : null,
      entry_version: row.is_in_my_library ? row.entry_version : null,
      membership_state: row.is_in_my_library ? row.membership_state : null,
    })
  }
  return result
}

// Owns only cache invalidation and request attribution. The DB owns membership.
export function createMembershipLookup(
  fetchStatuses,
  { now = () => performance.now(), ttl = 30000, limit = 500, protectedKeys = () => [] } = {}
) {
  const rows = ref(new Map()),
    loading = ref(new Set()),
    errors = ref(new Map()),
    revision = ref(0)
  let owner = '',
    epoch = 0,
    sequence = 0
  let scheduled = null
  const tickets = new Map(),
    batches = new Map()
  function bounded(map) {
    const protectedSet = new Set(protectedKeys())
    for (const key of map.keys()) {
      if (map.size <= limit) break
      if (!protectedSet.has(key)) map.delete(key)
    }
    return map
  }
  function prune() {
    if (rows.value.size > limit) rows.value = bounded(new Map(rows.value))
    if (errors.value.size > limit) errors.value = bounded(new Map(errors.value))
  }
  function reset(identity = '') {
    owner = identity
    scheduled = null
    epoch++
    revision.value++
    rows.value = new Map()
    loading.value = new Set()
    errors.value = new Map()
    tickets.clear()
    batches.clear()
  }
  function invalidate() {
    reset(owner)
  }
  function get(avid) {
    return rows.value.get(canonical(avid))?.value || null
  }
  async function chunk(avids, force, expectedEpoch) {
    const needed = avids.filter(
      (avid) => force || !rows.value.has(avid) || now() - rows.value.get(avid).time >= ttl
    )
    if (!needed.length) return
    const key = JSON.stringify(needed)
    if (batches.has(key)) return batches.get(key)
    const ticket = ++sequence
    needed.forEach((avid) => tickets.set(avid, ticket))
    loading.value = new Set([...loading.value, ...needed])
    errors.value = new Map([...errors.value].filter(([avid]) => !needed.includes(avid)))
    const operation = Promise.resolve().then(async () => {
      try {
        if (epoch !== expectedEpoch) return
        const response = await fetchStatuses(needed)
        if (epoch !== expectedEpoch) return
        const values = checkedStatuses(response.data, needed)
        const next = new Map(rows.value)
        let changed = false
        for (const [avid, value] of values) {
          if (tickets.get(avid) !== ticket) continue
          const previous = next.get(avid)?.value
          if (previous && Object.keys(value).some((key) => previous[key] !== value[key]))
            changed = true
          next.delete(avid)
          next.set(avid, { value, time: now() })
        }
        rows.value = bounded(next)
        if (changed) revision.value++
      } catch (error) {
        if (epoch !== expectedEpoch) return
        const next = new Map(errors.value)
        for (const avid of needed)
          if (tickets.get(avid) === ticket)
            next.set(avid, error.message || '无法确认我的资源库状态，请重试')
        errors.value = bounded(next)
      } finally {
        if (epoch === expectedEpoch) {
          loading.value = new Set([...loading.value].filter((avid) => tickets.get(avid) !== ticket))
          for (const avid of needed) if (tickets.get(avid) === ticket) tickets.delete(avid)
          if (batches.get(key) === operation) batches.delete(key)
        }
      }
    })
    batches.set(key, operation)
    return operation
  }
  async function load(avids, { force = false } = {}) {
    if (!owner) return { ignored: true }
    const expectedEpoch = epoch
    const identities = [...new Set(avids.map(canonical).filter(Boolean))]
    for (let offset = 0; offset < identities.length; offset += 100) {
      if (epoch !== expectedEpoch) return { ignored: true }
      await chunk(identities.slice(offset, offset + 100), force, expectedEpoch)
    }
    return { ignored: epoch !== expectedEpoch }
  }
  function schedule(avids, { force = false } = {}) {
    if (!owner) return Promise.resolve({ ignored: true })
    if (!scheduled) {
      const batch = { epoch, avids: new Set(), force: false, promise: null }
      batch.promise = Promise.resolve().then(() => {
        if (scheduled === batch) scheduled = null
        if (epoch !== batch.epoch) return { ignored: true }
        return load([...batch.avids], { force: batch.force })
      })
      scheduled = batch
    }
    for (const avid of avids) if (canonical(avid)) scheduled.avids.add(canonical(avid))
    scheduled.force ||= force
    return scheduled.promise
  }
  return { rows, loading, errors, revision, reset, invalidate, get, load, schedule, prune }
}
