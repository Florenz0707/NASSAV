import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { settingsApi } from '../src/api/index.js'
import { useSettingsStore } from '../src/features/settings/stores/settings.js'

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

test('settings reset invalidates former-user load/save and enables a fresh login load', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    originalGet = settingsApi.get,
    originalUpdate = settingsApi.update
  const pending = [],
    saving = deferred()
  settingsApi.get = () => {
    const next = deferred()
    pending.push(next)
    return next.promise
  }
  settingsApi.update = () => saving.promise
  try {
    const old = store.loadSettings()
    store.colorMode = 'light'
    const oldSave = store.saveSettings()
    store.reset()
    assert.equal(store.colorMode, 'dark')
    const current = store.loadSettings()
    pending[0].resolve({ data: { color_mode: 'light', font_family: 'former' } })
    assert.equal((await old).ignored, true)
    assert.equal(store.fontFamily, 'Mplus2')
    saving.resolve({ data: {} })
    assert.equal((await oldSave).ignored, true)
    pending[1].resolve({ data: { color_mode: 'dark', font_family: 'current' } })
    assert.equal((await current).success, true)
    assert.equal(store.fontFamily, 'current')
    assert.equal(store.loaded, true)
    assert.equal((await store.loadSettings()).cached, true)
  } finally {
    settingsApi.get = originalGet
    settingsApi.update = originalUpdate
  }
})

test('out-of-order forced settings loads retain the latest request and ignore former-user failures', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    original = settingsApi.get,
    requests = []
  settingsApi.get = () => {
    const next = deferred()
    requests.push(next)
    return next.promise
  }
  try {
    const first = store.loadSettings(),
      latest = store.loadSettings(true)
    requests[0].resolve({ data: { color_mode: 'light' } })
    await first
    const shared = store.loadSettings()
    assert.equal(requests.length, 2)
    requests[1].resolve({ data: { font_family: 'latest' } })
    await Promise.all([latest, shared])
    assert.equal(store.fontFamily, 'latest')
    const old = store.loadSettings(true)
    store.reset()
    requests[2].reject({ message: 'former account' })
    assert.equal((await old).ignored, true)
    assert.equal(store.loaded, false)
  } finally {
    settingsApi.get = original
  }
})

test('resource list reset clears private flags and rejects the old account response', async () => {
  const { createResourceList } = await import('../src/features/resources/stores/resourceList.js')
  const requests = []
  const list = createResourceList({
    getList: () => {
      const next = deferred()
      requests.push(next)
      return next.promise
    },
  })
  const old = list.fetchResources()
  list.resetResourceList()
  const current = list.fetchResources()
  requests[1].resolve({ data: [{ avid: 'CURRENT', watched: false }] })
  await current
  requests[0].resolve({ data: [{ avid: 'FORMER', watched: true }] })
  await old
  assert.equal(list.resources.value[0].avid, 'CURRENT')
  list.resetResourceList()
  assert.deepEqual(list.resources.value, [])
  assert.equal(list.pagination.value.total, 0)
})
