import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { viewingApi } from '../src/api/viewing.js'
import { personalDataChanged } from '../src/shared/lib/personalDataEvents.js'
import { useViewingStore } from '../src/features/viewing/stores/viewing.js'
function deferred() {
  let resolve, reject
  const promise = new Promise((a, b) => {
    resolve = a
    reject = b
  })
  return { promise, resolve, reject }
}
test('viewing cache deduplicates, expires, bounds pages and isolates owner/mutation epochs', async () => {
  setActivePinia(createPinia())
  const store = useViewingStore(),
    original = viewingApi.list,
    originalNow = Date.now
  let now = 10000,
    calls = 0
  Date.now = () => now
  viewingApi.list = async (kind, page) => {
    calls++
    return { data: [{ avid: `${kind}-${page}` }] }
  }
  try {
    await Promise.all([store.list('history', 1, 15), store.list('history', 1, 15)])
    assert.equal(calls, 1)
    now += 29999
    await store.list('history', 1, 15)
    assert.equal(calls, 1)
    now++
    await store.list('history', 1, 15)
    assert.equal(calls, 2)
    await store.list('history', 1, 15, true)
    assert.equal(calls, 3)
    personalDataChanged({})
    await store.list('history', 1, 15)
    assert.equal(calls, 4)
    for (let page = 2; page <= 10; page++) await store.list('history', page, 15)
    await store.list('history', 1, 15)
    assert.equal(calls, 14)
    const old = deferred(),
      fresh = deferred()
    viewingApi.list = () => old.promise
    store.reset()
    const stale = store.list('history', 1, 15)
    store.reset()
    viewingApi.list = () => fresh.promise
    const current = store.list('history', 1, 15)
    fresh.resolve({ data: ['new owner'] })
    await current
    old.resolve({ data: ['old owner'] })
    assert.equal(await stale, null)
    assert.deepEqual((await store.list('history', 1, 15)).data, ['new owner'])
  } finally {
    viewingApi.list = original
    Date.now = originalNow
    store.$dispose()
  }
})
test('viewing cache does not cache failure and a late forced query cannot replace latest', async () => {
  setActivePinia(createPinia())
  const store = useViewingStore(),
    original = viewingApi.list
  try {
    viewingApi.list = async () => {
      throw new Error('offline')
    }
    await assert.rejects(store.list('history', 1, 15), /offline/)
    const old = deferred(),
      fresh = deferred()
    viewingApi.list = () => old.promise
    const stale = store.list('history', 1, 15)
    viewingApi.list = () => fresh.promise
    const latest = store.list('history', 1, 15, true)
    fresh.resolve({ data: ['latest'] })
    await latest
    old.resolve({ data: ['stale'] })
    assert.equal(await stale, null)
    assert.deepEqual((await store.list('history', 1, 15)).data, ['latest'])
  } finally {
    viewingApi.list = original
    store.$dispose()
  }
})
