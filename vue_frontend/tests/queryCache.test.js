import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createQueryCache } from '../src/shared/lib/queryCache.js'
import { createResourceList } from '../src/features/resources/stores/resourceList.js'
import { createDirectoryStore } from '../src/features/catalog/stores/directoryStore.js'
import { createPinia, setActivePinia } from 'pinia'
const deferred = () => {
  let resolve
  const promise = new Promise((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}
test('query cache bounds pages, expires, clones values and rejects an invalidated pending result', async () => {
  let now = 0,
    calls = 0
  const cache = createQueryCache({ now: () => now, ttl: 30, limit: 2 })
  const load = async () => ({ data: [++calls] })
  const one = await cache.read('one', load)
  one.data[0] = 'mutated'
  assert.deepEqual((await cache.read('one', load)).data, [1])
  now = 30
  assert.equal(cache.peek('one').fresh, false)
  await cache.read('one', load)
  await cache.read('two', load)
  await cache.read('three', load)
  assert.equal(cache.peek('one'), null)
  const old = deferred(),
    fresh = deferred()
  const stale = cache.read('pending', () => old.promise)
  cache.clear()
  const current = cache.read('pending', () => fresh.promise)
  fresh.resolve({ data: ['new owner'] })
  await current
  old.resolve({ data: ['old owner'] })
  assert.equal(await stale, null)
  assert.deepEqual((await cache.read('pending', load)).data, ['new owner'])
})
for (const kind of ['resources', 'actors', 'genres']) {
  test(`${kind}: page1/page2/page1 reuses data; force refresh and owner reset are respected`, async () => {
    setActivePinia(createPinia())
    const requests = []
    const api = {
      getList: async (params) => {
        requests.push(params)
        return {
          data: [{ avid: `P-${params.page}`, id: params.page }],
          pagination: { page: params.page, total: 30, pages: 2 },
        }
      },
    }
    const raw =
      kind === 'resources' ? createResourceList(api) : createDirectoryStore(`cache-${kind}`, api)()
    const load = kind === 'resources' ? (p) => raw.fetchResources(p) : (p) => raw.load(p)
    const rows = () => (kind === 'resources' ? raw.resources.value : raw.groups)
    const reset = () => (kind === 'resources' ? raw.resetResourceList() : raw.reset())
    await load({ page: 1 })
    await load({ page: 2 })
    await load({ page: 1 })
    assert.equal(requests.length, 2)
    assert.equal(rows()[0].id, 1)
    rows()[0].id = 999
    await load({ page: 1 })
    assert.equal(rows()[0].id, 1)
    await load({ page: 1, force: true })
    assert.equal(requests.length, 3)
    reset()
    await load({ page: 1 })
    assert.equal(requests.length, 4)
    const pending = deferred()
    api.getList = () => pending.promise
    const one = load({ page: 5 }),
      two = load({ page: 5 })
    pending.resolve({ data: [{ id: 5 }] })
    await Promise.all([one, two])
    assert.equal(rows()[0].id, 5)
  })
}

test('expired list retains cached rows while refreshing and refresh bypasses every cached page', async () => {
  let now = 10000
  const original = Date.now
  Date.now = () => now
  try {
    const calls = []
    const api = {
      getList: async (params) => {
        calls.push(params.page)
        return { data: [{ avid: `P-${params.page}` }], pagination: { page: params.page } }
      },
    }
    const store = createResourceList(api)
    await store.fetchResources({ page: 1 })
    await store.fetchResources({ page: 2 })
    now += 30000
    const pending = deferred()
    api.getList = () => pending.promise
    const refresh = store.fetchResources({ page: 1 })
    assert.equal(store.resources.value[0].avid, 'P-1')
    assert.equal(store.loading.value, true)
    pending.resolve({ data: [{ avid: 'updated' }] })
    await refresh
    api.getList = async (params) => {
      calls.push(params.page)
      return { data: [] }
    }
    await store.refresh()
    await store.fetchResources({ page: 2 })
    assert.deepEqual(calls, [1, 2, 1, 2])
  } finally {
    Date.now = original
  }
})

test('failed reads are retried; concurrent reads share one transport and forced reads win', async () => {
  const cache = createQueryCache(),
    old = deferred(),
    latest = deferred()
  let calls = 0
  await assert.rejects(
    cache.read('a', () => Promise.reject(new Error('offline'))),
    /offline/
  )
  const a = cache.read('a', () => {
    calls++
    return old.promise
  })
  const b = cache.read('a', () => {
    calls++
    return old.promise
  })
  assert.equal(calls, 1)
  const forced = cache.read('a', () => latest.promise, { force: true })
  latest.resolve({ value: 'latest' })
  await forced
  old.resolve({ value: 'old' })
  assert.equal(await a, null)
  assert.equal(await b, null)
  assert.equal((await cache.read('a', () => null)).value, 'latest')
})

test('metadata and source reads deduplicate but never reuse another login request generation', async () => {
  const { default: api, invalidateSessionRequests } = await import('../src/api/client.js')
  const { resourceApi } = await import('../src/api/resources.js')
  const { sourceApi } = await import('../src/api/sources.js')
  const adapter = api.defaults.adapter,
    requests = []
  api.defaults.adapter = async (config) => {
    requests.push(config.url)
    return {
      status: 200,
      headers: {},
      config,
      data: { code: 200, data: { title: `version-${requests.length}` } },
    }
  }
  try {
    resourceApi.invalidateMetadataCache()
    await Promise.all([resourceApi.getMetadata('A-1'), resourceApi.getMetadata('A-1')])
    await sourceApi.getList()
    await sourceApi.getList()
    assert.deepEqual(requests, ['/resource/metadata', '/source/list'])
    invalidateSessionRequests()
    await resourceApi.getMetadata('A-1')
    await sourceApi.getList()
    assert.equal(requests.length, 4)
    await resourceApi.getMetadata('A-1', true)
    assert.equal(requests.length, 5)
  } finally {
    api.defaults.adapter = adapter
    resourceApi.invalidateMetadataCache()
    invalidateSessionRequests()
  }
})
