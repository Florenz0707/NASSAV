import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runRecommendationJob } from '../src/features/recommendations/lib/recommendationJob.js'

function snapshot(state, version = 1, result = null) {
  return { data: { job_id: 'job', state, version, result, message: '来源暂不可用' } }
}

function context(controller = new AbortController()) {
  return { signal: controller.signal, onJob: () => {}, onSnapshot: () => {}, wait: async () => {} }
}

test('polling ignores old versions and only returns terminal success', async () => {
  const seen = []
  const responses = [
    snapshot('failed', 0),
    snapshot('running', 2),
    snapshot('succeeded', 3, { items: [{ avid: 'NEW' }] }),
  ]
  const api = { startJob: async () => snapshot('queued'), getJob: async () => responses.shift() }
  const result = await runRecommendationJob(
    api,
    {},
    { ...context(), onSnapshot: (job) => seen.push(job.state) }
  )
  assert.deepEqual(seen, ['queued', 'running', 'succeeded'])
  assert.deepEqual(result.data.items, [{ avid: 'NEW' }])
})

test('abandoning a pending submission cancels the returned backend ID', async () => {
  const controller = new AbortController()
  let resolve
  const cancelled = []
  const api = {
    startJob: () =>
      new Promise((done) => {
        resolve = done
      }),
    cancelJob: async (id) => cancelled.push(id),
  }
  const pending = runRecommendationJob(api, {}, context(controller))
  controller.abort()
  resolve(snapshot('queued'))
  assert.equal(await pending, null)
  assert.deepEqual(cancelled, ['job'])
})

test('cancelled and failed snapshots cannot be reported as successful empty results', async () => {
  assert.equal(
    await runRecommendationJob({ startJob: async () => snapshot('cancelled') }, {}, context()),
    null
  )
  await assert.rejects(
    runRecommendationJob({ startJob: async () => snapshot('failed') }, {}, context()),
    /来源暂不可用/
  )
})

test('wrong job identity is rejected', async () => {
  const api = {
    startJob: async () => snapshot('queued'),
    getJob: async () => ({ data: { job_id: 'another', version: 2, state: 'succeeded' } }),
  }
  await assert.rejects(runRecommendationJob(api, {}, context()), /身份不匹配/)
})
