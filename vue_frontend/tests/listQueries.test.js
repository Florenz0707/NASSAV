import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { actorApi, genreApi, resourceApi } from '../src/api/index.js'
import { useActorGroupsStore } from '../src/features/catalog/stores/actorGroups.js'
import { useGenreGroupsStore } from '../src/features/catalog/stores/genreGroups.js'
import { useResourceStore } from '../src/features/resources/stores/resource.js'

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

for (const [name, api, useStore, action, field, cancel] of [
  [
    'resources',
    resourceApi,
    useResourceStore,
    'fetchResources',
    'resources',
    'cancelResourceQuery',
  ],
  ['actors', actorApi, useActorGroupsStore, 'load', 'groups', 'cancel'],
  ['genres', genreApi, useGenreGroupsStore, 'load', 'groups', 'cancel'],
]) {
  test(`${name}: stale success/failure cannot change the newest query or loading`, async () => {
    setActivePinia(createPinia())
    const store = useStore()
    const original = api.getList
    const requests = []
    api.getList = () => {
      const next = deferred()
      requests.push(next)
      return next.promise
    }
    try {
      const old = store[action]({ search: 'old' })
      const latest = store[action]({ search: 'new' })
      requests[0].reject(new Error('old error'))
      await old
      assert.equal(store.loading, true)
      assert.equal(store.error, null)
      requests[1].resolve({ data: [{ avid: 'NEW', id: 2 }] })
      await latest
      assert.equal(store[field][0].id, 2)
      const late = store[action]({ search: 'late' })
      const current = store[action]({ search: 'current' })
      requests[3].resolve({ data: [{ id: 4 }] })
      await current
      requests[2].resolve({ data: [{ id: 3 }] })
      await late
      assert.equal(store[field][0].id, 4)
      const removed = store[action]()
      store[cancel]()
      requests[4].resolve({ data: [{ id: 5 }] })
      await removed
      assert.equal(store[field][0].id, 4)
      assert.equal(store.loading, false)
    } finally {
      api.getList = original
    }
  })
}
