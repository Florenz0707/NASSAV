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

test('saving sends only changed settings, leaving GET defaults as implicit overrides', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    originalGet = settingsApi.get,
    originalUpdate = settingsApi.update,
    calls = []
  settingsApi.get = async () => ({
    data: {
      color_mode: 'dark',
      enable_avatar: 'true',
      display_title: 'source_title',
      font_family: 'Mplus2',
      search_result_display_style: 'grid',
      default_external_search_source: 'jable',
    },
  })
  settingsApi.update = async (body) => {
    calls.push(body)
    return { data: {} }
  }
  try {
    await store.loadSettings()
    assert.equal((await store.saveSettings()).unchanged, true)
    assert.equal(calls.length, 0)
    store.colorMode = 'light'
    await store.saveSettings()
    assert.deepEqual(calls, [{ color_mode: 'light' }])
    await store.saveSettings()
    assert.equal(calls.length, 1)
    store.showActorAvatar = false
    await store.saveSettings()
    assert.deepEqual(calls[1], { enable_avatar: 'false' })
  } finally {
    settingsApi.get = originalGet
    settingsApi.update = originalUpdate
  }
})

test('failed partial save retains changed fields and edits made during save are still dirty', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    original = settingsApi.update,
    calls = [],
    responses = []
  settingsApi.update = (body) => {
    calls.push(body)
    const next = deferred()
    responses.push(next)
    return next.promise
  }
  const originalLog = console.error
  console.error = () => {}
  try {
    store.colorMode = 'light'
    const failed = store.saveSettings()
    responses[0].reject({ message: 'temporary failure' })
    await assert.rejects(failed)
    const retry = store.saveSettings()
    assert.deepEqual(calls[1], { color_mode: 'light' })
    store.fontFamily = 'Custom Font'
    responses[1].resolve({ data: {} })
    await retry
    const next = store.saveSettings()
    assert.deepEqual(calls[2], { font_family: 'Custom Font' })
    responses[2].resolve({ data: {} })
    await next
  } finally {
    settingsApi.update = original
    console.error = originalLog
  }
})

test('out-of-order saves cannot roll back the saved baseline', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    original = settingsApi.update,
    calls = [],
    responses = []
  settingsApi.update = (body) => {
    calls.push(body)
    const next = deferred()
    responses.push(next)
    return next.promise
  }
  try {
    store.colorMode = 'light'
    const old = store.saveSettings()
    store.showActorAvatar = false
    const latest = store.saveSettings()
    responses[1].resolve({ data: {} })
    await latest
    responses[0].resolve({ data: {} })
    assert.equal((await old).ignored, true)
    await store.saveSettings()
    assert.equal(calls.length, 2)
  } finally {
    settingsApi.update = original
  }
})

test('a former-player preference writer cannot save into a new login', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    original = settingsApi.update,
    calls = []
  settingsApi.update = async (patch) => {
    calls.push(patch)
  }
  try {
    const oldWriter = store.playbackPreferenceWriter()
    store.reset()
    await oldWriter({ volume: 0.2 })
    assert.equal(calls.length, 0)
    await store.playbackPreferenceWriter()({ volume: 0.4, muted: true })
    assert.deepEqual(calls, [{ playback_volume: 0.4, playback_muted: true }])
    assert.equal(store.playbackPreferences.volume, 0.4)
  } finally {
    settingsApi.update = original
  }
})

test('personal center saves only the selected settings section, preserving other drafts', async () => {
  setActivePinia(createPinia())
  const store = useSettingsStore(),
    original = settingsApi.update,
    calls = []
  settingsApi.update = async (body) => {
    calls.push(body)
    return { data: {} }
  }
  try {
    store.colorMode = 'light'
    store.playbackPreferences.rate = 1.5
    store.recommendationPreferences.strategy = 'hybrid'
    await store.saveSettings('playback')
    assert.deepEqual(calls[0], { playback_rate: 1.5 })
    await store.saveSettings('general')
    assert.deepEqual(calls[1], { color_mode: 'light' })
    assert.equal((await store.saveSettings('general')).unchanged, true)
    await store.saveSettings()
    assert.deepEqual(calls[2], { recommendation_strategy: 'hybrid' })
  } finally {
    settingsApi.update = original
  }
})
