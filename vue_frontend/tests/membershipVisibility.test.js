import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { useMembershipsStore } from '../src/features/library/stores/memberships.js'
import { libraryApi } from '../src/api/library.js'

test('visible membership registration owns one timer and old cleanup cannot stop a new login', async () => {
  const originalInterval = globalThis.setInterval,
    originalClear = globalThis.clearInterval,
    originalFetch = libraryApi.membershipStatuses
  const timers = new Map(),
    requests = []
  let serial = 0
  globalThis.setInterval = (callback) => {
    const id = ++serial
    timers.set(id, callback)
    return id
  }
  globalThis.clearInterval = (id) => timers.delete(id)
  libraryApi.membershipStatuses = async (avids) => {
    requests.push(avids)
    return { data: avids.map((avid) => ({ avid, is_in_my_library: false, is_available: false })) }
  }
  setActivePinia(createPinia())
  const store = useMembershipsStore()
  try {
    store.reset('a')
    const releaseFirst = store.retain('a-1'),
      releaseSecond = store.retain('b-1')
    assert.equal(timers.size, 1)
    const tick = [...timers.values()][0]
    tick()
    await new Promise((resolve) => setImmediate(resolve))
    assert.deepEqual(requests, [['A-1', 'B-1']])
    store.invalidate()
    assert.equal(timers.size, 1, 'Domain invalidation must preserve mounted registrations')
    store.reset('b')
    assert.equal(timers.size, 0)
    const releaseNew = store.retain('c-1')
    releaseFirst()
    releaseSecond()
    assert.equal(timers.size, 1, 'Old components cannot stop the new login timer')
    releaseNew()
    assert.equal(timers.size, 0)
  } finally {
    store.reset()
    globalThis.setInterval = originalInterval
    globalThis.clearInterval = originalClear
    libraryApi.membershipStatuses = originalFetch
  }
})
