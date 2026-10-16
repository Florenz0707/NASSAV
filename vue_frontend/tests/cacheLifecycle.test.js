import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { readSessionCache, writeSessionCache } from '../src/shared/lib/sessionCache.js'
import {
  saveRecommendationViewState,
  restoreRecommendationViewState,
} from '../src/features/recommendations/stores/recommendationViewState.js'
import { useViewingStore } from '../src/features/viewing/stores/viewing.js'
import { viewingApi, settingsApi } from '../src/api/index.js'
import { personalDataChanged } from '../src/shared/lib/personalDataEvents.js'
import { useSettingsStore } from '../src/features/settings/stores/settings.js'
import { pollExternalSearch } from '../src/features/external-search/composables/useExternalSearchTask.js'
const disk = () => {
  const map = new Map()
  return {
    get length() {
      return map.size
    },
    key: (index) => [...map.keys()][index],
    getItem: (key) => map.get(key) || null,
    setItem: (key, value) => map.set(key, value),
    removeItem: (key) => map.delete(key),
  }
}
const deferred = () => {
  let resolve
  const promise = new Promise((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}
test('session cache expires absolutely, bounds storage and tolerates quota/security errors', () => {
  const storage = disk()
  for (let i = 0; i < 4; i++)
    writeSessionCache(storage, `q:${i}`, { page: i }, { prefix: 'q:', limit: 2, now: i, ttl: 10 })
  assert.equal(storage.length, 2)
  assert.equal(readSessionCache(storage, 'q:0', 4), null)
  assert.equal(readSessionCache(storage, 'q:2', 12), null)
  assert.equal(readSessionCache(storage, 'q:3', 12).value.page, 3)
  const unavailable = {
    getItem() {
      throw Error('denied')
    },
    setItem() {
      throw Error('quota')
    },
    removeItem() {
      throw Error('denied')
    },
  }
  assert.equal(readSessionCache(unavailable, 'q'), null)
  assert.equal(writeSessionCache(unavailable, 'q', {}), false)
  assert.equal(writeSessionCache(storage, 'huge', 'x'.repeat(100), { maxBytes: 10 }), false)
})
test('recommendation scroll/feedback saves do not extend the same results indefinitely', () => {
  const storage = disk(),
    original = Date.now
  let now = 10000
  Date.now = () => now
  try {
    const state = { items: [{ avid: 'A-1', snapshot_id: 1 }], cacheExpiresAt: now + 1800000 }
    saveRecommendationViewState(state, storage, 'a')
    now += 1000000
    saveRecommendationViewState({ ...state, scrollY: 100 }, storage, 'a')
    assert.equal(restoreRecommendationViewState(storage, 'b'), null)
    now += 800001
    assert.equal(restoreRecommendationViewState(storage, 'a'), null)
    saveRecommendationViewState(state, storage, 'a')
    assert.equal(restoreRecommendationViewState(storage, 'a'), null)
    saveRecommendationViewState({ items: [{ avid: 'A-2', snapshot_id: 2 }] }, storage, 'a')
    assert.equal(restoreRecommendationViewState(storage, 'a').items[0].avid, 'A-2')
  } finally {
    Date.now = original
  }
})
test('history mutation does not evict watch-later; a note edit does not evict either list', async () => {
  setActivePinia(createPinia())
  const store = useViewingStore(),
    original = viewingApi.list,
    calls = []
  viewingApi.list = async (kind) => {
    calls.push(kind)
    return { data: [] }
  }
  try {
    await store.list('history', 1, 15)
    await store.list('watch-later', 1, 15)
    personalDataChanged(null, ['history'])
    await store.list('watch-later', 1, 15)
    assert.deepEqual(calls, ['history', 'watch-later'])
    await store.list('history', 1, 15)
    personalDataChanged(null, ['resource-detail'])
    await store.list('history', 1, 15)
    await store.list('watch-later', 1, 15)
    assert.equal(calls.length, 3)
  } finally {
    viewingApi.list = original
    store.$dispose()
  }
})
test('settings expire and revalidate without overwriting an unsaved edit or a newer save', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    get = settingsApi.get,
    update = settingsApi.update,
    original = Date.now
  let now = 10000,
    calls = 0
  Date.now = () => now
  settingsApi.get = async () => {
    calls++
    return { data: { font_family: 'Mplus2' } }
  }
  settingsApi.update = async () => ({ data: {} })
  try {
    await store.loadSettings()
    await store.loadSettings()
    assert.equal(calls, 1)
    now += 300000
    await store.loadSettings()
    assert.equal(calls, 2)
    store.fontFamily = 'local draft'
    store.invalidate()
    await store.loadSettings()
    assert.equal(calls, 2)
    assert.equal(store.fontFamily, 'local draft')
    await store.saveSettings('general')
    const pending = deferred()
    settingsApi.get = () => pending.promise
    store.invalidate()
    const old = store.loadSettings()
    store.fontFamily = 'new saved'
    await store.saveSettings('general')
    pending.resolve({ data: { font_family: 'remote old' } })
    assert.equal((await old).ignored, true)
    assert.equal(store.fontFamily, 'new saved')
  } finally {
    settingsApi.get = get
    settingsApi.update = update
    Date.now = original
    store.$dispose()
  }
})
test('external search exposes server remaining lifetime without changing legacy result payloads', async () => {
  const result = { data: { external_results: [] }, pagination: { page: 1 } }
  const output = await pollExternalSearch(
    {},
    {
      signal: new AbortController().signal,
      current: () => true,
      onStatus: () => {},
      api: {
        submit: async () => ({
          data: {
            task_id: 'id',
            token: 'token',
            state: 'succeeded',
            result,
            result_cache_ttl_seconds: 17,
          },
        }),
      },
    }
  )
  assert.equal(output.cache_ttl_seconds, 17)
  assert.deepEqual(output.data, result.data)
})
