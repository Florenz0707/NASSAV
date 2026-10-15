import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { createDirectoryStore } from '../src/features/catalog/stores/directoryStore.js'
import { useResourceStore } from '../src/features/resources/stores/resource.js'
import { useDownloadQueueStore } from '../src/features/resources/stores/downloadQueue.js'

function storage() {
  const data = new Map()
  return {
    getItem: (key) => data.get(key) || null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  }
}

test('changing cache identity clears directory results and rejects the previous request', async () => {
  setActivePinia(createPinia())
  const pending = []
  const useDirectory = createDirectoryStore('session-directory', {
    getList: () => new Promise((resolve) => pending.push(resolve)),
  })
  const store = useDirectory()
  store.groups = [{ name: 'former-private-actor' }]
  const old = store.load()
  store.reset()
  assert.deepEqual(store.groups, [])
  const current = store.load()
  pending[0]({ data: [{ name: 'former-private-actor' }] })
  await old
  assert.deepEqual(store.groups, [])
  pending[1]({ data: [{ name: 'current-actor' }] })
  await current
  assert.equal(store.groups[0].name, 'current-actor')
})

test('legacy task storage and in-memory titles are not restored into another login', async () => {
  globalThis.localStorage = storage()
  localStorage.setItem(
    'nassav:scrape-jobs:v1',
    JSON.stringify([{ task_id: 'unowned-old', status_token: 'old-token', state: 'running' }])
  )
  setActivePinia(createPinia())
  const resources = useResourceStore()
  const queue = useDownloadQueueStore()
  resources.beginSession('login-a')
  resources.registerScrapeBatch([
    { code: 202, task_id: 'private-a', avid: 'AAA-1', action: 'add', status_token: 'token-a' },
  ])
  assert.ok(localStorage.getItem('nassav:scrape-jobs:v2:login-a').includes('private-a'))
  queue.titleCache.set('AAA-1', { metadata: { title: 'private-a' } })
  queue.activeTasks = [{ avid: 'AAA-1' }]
  queue.dismissTasks(['private-a'])
  assert.equal(queue.isTracked({ task_id: 'private-a' }), false)
  resources.beginSession('login-b')
  queue.beginSession('login-b')
  await resources.restoreScrapeJobs()
  assert.equal(resources.visibleScrapeJobs.length, 0)
  assert.equal(queue.titleCache.size, 0)
  assert.deepEqual(queue.activeTasks, [])
  assert.equal(queue.isTracked({ task_id: 'private-a' }), true)
  resources.stopScrapeTracking()
  queue.stopTracking()
})

test('progress drafts survive same-login reload but cannot cross login namespaces or revive after logout', async () => {
  const { createProgressDrafts, clearPlaybackDrafts } =
    await import('../src/features/playback/lib/progressDrafts.js')
  const rows = new Map()
  const disk = {
    get length() {
      return rows.size
    },
    key: (index) => [...rows.keys()][index],
    getItem: (key) => rows.get(key) || null,
    setItem: (key, value) => rows.set(key, value),
    removeItem: (key) => rows.delete(key),
  }
  let valid = true
  const draft = createProgressDrafts(
    disk,
    () => 100,
    'login-a',
    () => valid
  )
  const snapshot = { ledger_key: 'ledger', version: 1, writer_generation: 2 }
  const body = {
    position_seconds: 25,
    duration_seconds: 100,
    writer_generation: 2,
    sequence: 1,
    expected_version: 1,
  }
  draft.put(snapshot, body)
  assert.equal(createProgressDrafts(disk, () => 101, 'login-a').get(snapshot).position_seconds, 25)
  assert.equal(createProgressDrafts(disk, () => 101, 'login-b').get(snapshot), null)
  valid = false
  clearPlaybackDrafts(disk)
  draft.put(snapshot, body)
  assert.equal(rows.size, 0)
  assert.equal(draft.get(snapshot), null)
})

test('an old submit failure cannot clear the new login loading, errors or download status', async () => {
  const { resourceApi, downloadApi } = await import('../src/api/index.js')
  const originalAdd = resourceApi.addNew,
    originalDownload = downloadApi.submitDownload
  const adding = [],
    downloading = []
  resourceApi.addNew = () => new Promise((resolve, reject) => adding.push({ resolve, reject }))
  downloadApi.submitDownload = () =>
    new Promise((resolve, reject) => downloading.push({ resolve, reject }))
  setActivePinia(createPinia())
  const store = useResourceStore()
  try {
    store.beginSession('login-a')
    const oldAdd = store.addResource('AAA-1')
    const oldDownload = store.submitDownload('AAA-1')
    const rejectedAdd = assert.rejects(oldAdd),
      rejectedDownload = assert.rejects(oldDownload)
    store.beginSession('login-b')
    const nextAdd = store.addResource('AAA-1')
    const nextDownload = store.submitDownload('AAA-1')
    adding[0].reject(new Error('old add'))
    downloading[0].reject(new Error('old download'))
    await Promise.all([rejectedAdd, rejectedDownload])
    assert.equal(store.loading, true)
    assert.equal(store.error, null)
    assert.equal(store.downloadStates.get('AAA-1'), 'submitting')
    adding[1].resolve({ code: 202, data: {} })
    downloading[1].resolve({ code: 202, data: {} })
    await Promise.all([nextAdd, nextDownload])
    assert.equal(store.loading, false)
    assert.equal(store.downloadStates.get('AAA-1'), 'downloading')
  } finally {
    resourceApi.addNew = originalAdd
    downloadApi.submitDownload = originalDownload
    store.stopScrapeTracking()
  }
})
