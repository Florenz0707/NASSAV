import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sourceApi } from '../src/api/index.js'
import {
  useExternalSearchSources,
  createSearchRequestGuard,
} from '../src/composables/useExternalSearchSources.js'

function storageWith(value) {
  const values = new Map(value ? [['external_search_source', value]] : [])
  return { getItem: (key) => values.get(key), setItem: (key, item) => values.set(key, item) }
}

test('source options reflect enabled capabilities and restore a supported preference', async () => {
  const original = sourceApi.getSearchCapabilities
  sourceApi.getSearchCapabilities = async () => ({
    data: [
      { source: 'jable', label: 'Jable', actor: true, genre: true },
      { source: 'missav', label: 'MissAV', actor: true, genre: true, orderings: ['-views'] },
      { source: 'other', label: 'Other', actor: false, genre: false },
    ],
  })
  try {
    for (const entity of ['actor', 'genre']) {
      const storage = storageWith('missav')
      const state = useExternalSearchSources(entity, storage)
      await state.loadSearchSources()
      assert.equal(state.externalSource.value, 'missav')
      assert.deepEqual(
        state.sourceOptions.value.map((item) => item.value),
        ['jable', 'missav']
      )
      state.externalSource.value = 'jable'
      state.rememberSource()
      assert.equal(useExternalSearchSources(entity, storage).externalSource.value, 'jable')
    }
  } finally {
    sourceApi.getSearchCapabilities = original
  }
})

test('disabled preference falls back; no sources and discovery errors are explicit', async () => {
  const original = sourceApi.getSearchCapabilities
  try {
    const state = useExternalSearchSources('actor', storageWith('missav'))
    sourceApi.getSearchCapabilities = async () => ({ data: [{ source: 'jable', actor: true }] })
    await state.loadSearchSources()
    assert.equal(state.externalSource.value, 'jable')
    sourceApi.getSearchCapabilities = async () => ({ data: [] })
    await state.loadSearchSources()
    assert.equal(state.externalSource.value, '')
    assert.ok(state.sourcesError.value)
    sourceApi.getSearchCapabilities = async () => {
      throw new Error('network failed')
    }
    await state.loadSearchSources()
    assert.equal(state.sourcesError.value, 'network failed')
  } finally {
    sourceApi.getSearchCapabilities = original
  }
})

test('a slow old-source response cannot overwrite a newer selection or unmounted view', async () => {
  const guard = createSearchRequestGuard()
  let resolveOld
  let displayed = ''
  const oldRequest = guard.begin()
  const oldResponse = new Promise((resolve) => {
    resolveOld = resolve
  })
  const pending = oldResponse.then((result) => {
    if (guard.current(oldRequest)) displayed = result
  })
  guard.invalidate()
  const current = guard.begin()
  if (guard.current(current)) displayed = 'MissAV results'
  resolveOld('Jable results')
  await pending
  assert.equal(displayed, 'MissAV results')
  guard.invalidate()
  assert.equal(guard.current(current), false)
})

test('actor and genre search allow multi-page browser time; ordinary list requests retain their timeout', async () => {
  const { default: axios } = await import('axios')
  const original = axios.defaults.adapter
  const requests = []
  axios.defaults.adapter = async (config) => {
    requests.push(config)
    return { config, status: 200, statusText: 'OK', headers: {}, data: { code: 200, data: [] } }
  }
  try {
    const { actorApi, genreApi, resourceApi } = await import('../src/api/index.js?timeout-test')
    await actorApi.getDetail(1, { source: 'missav' })
    await genreApi.getDetail(2, { source: 'jable' })
    await resourceApi.getList()
    assert.equal(requests[0].timeout, 450000)
    assert.equal(requests[1].timeout, 450000)
    assert.equal(requests[2].timeout, 30000)
    assert.equal(requests[0].params.source, 'missav')
    assert.equal(requests[1].params.source, 'jable')
  } finally {
    axios.defaults.adapter = original
  }
})
