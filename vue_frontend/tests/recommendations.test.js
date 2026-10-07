import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

const requests = []
let batch = 0
axios.defaults.adapter = async (config) => {
  requests.push({ url: config.url, method: config.method, data: config.data })
  let data = null
  if (config.url === '/recommendations/jobs') {
    batch += 1
    data = { job_id: String(batch), state: 'queued', version: 1 }
  } else if (/^\/recommendations\/jobs\/[^/]+$/.test(config.url)) {
    data = {
      job_id: config.url.split('/').at(-1),
      state: 'succeeded',
      version: 2,
      result: {
        items: [{ avid: 'REC-1' }, { avid: batch === 1 ? 'REC-2' : 'REC-3' }],
        seeds: [{ seed_type: 'actor', id: 1 }],
        meta: { batch },
      },
    }
  } else if (config.url.endsWith('/cancel')) {
    data = { state: 'cancelled' }
  } else if (config.url === '/recommendations/metrics') {
    data = { snapshot_count: batch }
  } else if (config.url === '/recommendations/feedback') {
    data = { feedback: JSON.parse(config.data).feedback }
  } else if (config.url === '/recommendations/avid-blocklist') {
    data = config.method === 'get' ? [] : { avid: 'REC-1' }
  } else if (config.url === '/recommendations/reset') {
    data = {}
  } else {
    throw new Error(`Unexpected request: ${config.method} ${config.url}`)
  }
  return { config, status: 200, statusText: 'OK', headers: {}, data: { code: 200, data } }
}

const { useRecommendationsStore } =
  await import('../src/features/recommendations/stores/recommendations.js')

test('recommendation batches merge by avid and feedback persists in store state', async () => {
  setActivePinia(createPinia())
  requests.length = 0
  batch = 0
  const store = useRecommendationsStore()
  await store.fetchRecommendations({ limit: 12 })
  await store.fetchRecommendations({ limit: 12 }, { append: true })
  assert.deepEqual(
    store.items.map((item) => item.avid),
    ['REC-1', 'REC-2', 'REC-3']
  )
  assert.equal(store.meta.batch, 2)
  await store.loadMetrics()
  assert.equal(store.metrics.snapshot_count, 2)

  const item = { avid: 'REC-1', snapshot_id: 7 }
  assert.equal(await store.submitFeedback(item, 'like'), 'like')
  assert.equal(store.feedbackByAvid['REC-1'], 'like')
  await store.submitFeedback(item, 'clear')
  assert.equal(store.feedbackByAvid['REC-1'], undefined)
  assert.equal(requests.filter((request) => request.url === '/recommendations/feedback').length, 2)
})

test('clearing the view keeps metrics while history reset uses the established payload', async () => {
  setActivePinia(createPinia())
  const store = useRecommendationsStore()
  await store.loadMetrics()
  store.items = [{ avid: 'REC-1' }]
  store.blockedAvids = new Set(['REC-1'])
  store.clearResults()
  assert.deepEqual(store.items, [])
  assert.equal(store.blockedAvids.size, 0)
  assert.ok(store.metrics)
  await store.resetHistory()
  const reset = requests.findLast((request) => request.url === '/recommendations/reset')
  assert.deepEqual(JSON.parse(reset.data), { preserve_blocklist: true })
})

const {
  saveRecommendationViewState,
  restoreRecommendationViewState,
  clearRecommendationViewState,
} = await import('../src/features/recommendations/stores/recommendationViewState.js')

test('recommendation view state survives reload and corrupt data is discarded', () => {
  const values = new Map()
  const storage = {
    setItem: (key, value) => values.set(key, value),
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
  }
  const state = { items: [{ avid: 'REC-1' }], feedbackByAvid: { 'REC-1': 'like' }, scrollY: 42 }
  saveRecommendationViewState(state, storage)
  assert.deepEqual(restoreRecommendationViewState(storage), state)
  clearRecommendationViewState(storage)
  assert.equal(restoreRecommendationViewState(storage), null)
  storage.setItem('nassav:recommendations:view-state', '{bad json')
  assert.equal(restoreRecommendationViewState(storage), null)
  assert.equal(storage.getItem('nassav:recommendations:view-state'), null)
})

test('resource blocklist mutation updates the store only after the API succeeds', async () => {
  setActivePinia(createPinia())
  const store = useRecommendationsStore()
  await store.setAvidBlocked('REC-1', true)
  assert.equal(store.blockedAvids.has('REC-1'), true)
  await store.setAvidBlocked('REC-1', false)
  assert.equal(store.blockedAvids.has('REC-1'), false)
  const mutations = requests.filter(
    (request) => request.url === '/recommendations/avid-blocklist' && request.method !== 'get'
  )
  assert.equal(mutations.at(-2).method, 'post')
  assert.equal(mutations.at(-1).method, 'delete')
  assert.equal(JSON.parse(mutations.at(-2).data).reason, 'manual')
})

test('late recommendation success and failure cannot replace a newer query or cleared results', async () => {
  const { recommendationApi } = await import('../src/api/index.js')
  const original = recommendationApi.startJob
  const pending = []
  recommendationApi.startJob = () =>
    new Promise((resolve, reject) => pending.push({ resolve, reject }))
  try {
    setActivePinia(createPinia())
    const store = useRecommendationsStore()
    const old = store.fetchRecommendations({ limit: 1 })
    const latest = store.fetchRecommendations({ limit: 2 })
    pending[1].resolve({
      data: { job_id: 'new', version: 1, state: 'succeeded', result: { items: [{ avid: 'NEW' }] } },
    })
    await latest
    pending[0].resolve({
      data: { job_id: 'old', version: 1, state: 'succeeded', result: { items: [{ avid: 'OLD' }] } },
    })
    assert.equal(await old, null)
    assert.deepEqual(store.items, [{ avid: 'NEW' }])
    const failing = store.fetchRecommendations({ limit: 3 })
    store.clearResults()
    pending[2].reject(new Error('late failure'))
    assert.equal(await failing, null)
    assert.deepEqual(store.items, [])
    assert.equal(store.loading, false)
    assert.equal(store.error, '')
  } finally {
    recommendationApi.startJob = original
  }
})

test('failed cancellation keeps the current job tracked and allows retry', async () => {
  const { recommendationApi } = await import('../src/api/index.js')
  const original = { startJob: recommendationApi.startJob, cancelJob: recommendationApi.cancelJob }
  let cancels = 0
  recommendationApi.startJob = async () => ({
    data: { job_id: 'running', version: 1, state: 'queued' },
  })
  recommendationApi.cancelJob = async () => {
    cancels++
    if (cancels === 1) throw new Error('取消未确认')
    return { data: { state: 'cancelled' } }
  }
  try {
    setActivePinia(createPinia())
    const store = useRecommendationsStore()
    const pending = store.fetchRecommendations({})
    await new Promise((resolve) => setTimeout(resolve, 0))
    await assert.rejects(store.cancelRecommendation(), /取消未确认/)
    assert.equal(store.loading, true)
    assert.equal(store.activeJobId, 'running')
    await store.cancelRecommendation()
    assert.equal(await pending, null)
    assert.equal(store.loading, false)
  } finally {
    Object.assign(recommendationApi, original)
  }
})

test('known failed terminal snapshots do not send a redundant cancel request', async () => {
  const { recommendationApi } = await import('../src/api/index.js')
  const original = { startJob: recommendationApi.startJob, cancelJob: recommendationApi.cancelJob }
  let cancels = 0
  recommendationApi.startJob = async () => ({
    data: { job_id: 'failed', version: 3, state: 'failed', message: '推荐超时' },
  })
  recommendationApi.cancelJob = async () => {
    cancels++
  }
  try {
    setActivePinia(createPinia())
    const store = useRecommendationsStore()
    await assert.rejects(store.fetchRecommendations({}), /推荐超时/)
    assert.equal(store.jobState, 'failed')
    assert.equal(cancels, 0)
    assert.equal(store.loading, false)
  } finally {
    Object.assign(recommendationApi, original)
  }
})

test('progress is owned by the current query and cleared on cancellation', async () => {
  const { recommendationApi } = await import('../src/api/index.js')
  const original = { startJob: recommendationApi.startJob, cancelJob: recommendationApi.cancelJob }
  recommendationApi.startJob = async () => ({
    data: {
      job_id: 'progress',
      version: 2,
      state: 'running',
      progress: { stage: 'details', verified_count: 4 },
    },
  })
  recommendationApi.cancelJob = async () => ({ data: { state: 'cancelled' } })
  try {
    setActivePinia(createPinia())
    const store = useRecommendationsStore()
    const pending = store.fetchRecommendations({})
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(store.progress.verified_count, 4)
    store.cancelQuery()
    assert.equal(await pending, null)
    assert.equal(store.progress, null)
  } finally {
    Object.assign(recommendationApi, original)
  }
})
