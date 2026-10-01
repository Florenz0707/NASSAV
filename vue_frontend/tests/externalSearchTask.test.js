import assert from 'node:assert/strict'
import { test } from 'node:test'
import { pollExternalSearch, waitForSearchPoll } from '../src/composables/useExternalSearchTask.js'

test('queued submission polls through running to a completed result', async () => {
  const states = []
  const result = { data: { external_results: [{ avid: 'TEST-123' }] }, pagination: { page: 1 } }
  const snapshots = [{ state: 'running' }, { state: 'succeeded', result }]
  const api = {
    submit: async () => ({ data: { state: 'queued', task_id: 'id', token: 'token' } }),
    getJob: async (id, token) => {
      assert.equal(id, 'id')
      assert.equal(token, 'token')
      return { data: snapshots.shift() }
    },
  }
  const response = await pollExternalSearch(
    {},
    {
      signal: new AbortController().signal,
      current: () => true,
      onStatus: (s) => states.push(s),
      api,
      wait: async () => {},
    }
  )
  assert.deepEqual(response, result)
  assert.deepEqual(states, ['queued', 'running', 'succeeded'])
})

test('switching sources aborts polling before an old response can be displayed', async () => {
  const controller = new AbortController()
  let calls = 0
  const result = await pollExternalSearch(
    {},
    {
      signal: controller.signal,
      current: () => true,
      onStatus: () => {},
      api: {
        submit: async () => ({ data: { state: 'queued' } }),
        getJob: async () => {
          calls += 1
        },
      },
      wait: async () => controller.abort(),
    }
  )
  assert.equal(result, null)
  assert.equal(calls, 0)
})

test('failed jobs expose the retry message; polling recovers from a transient network failure', async () => {
  let calls = 0
  const api = {
    submit: async () => ({ data: { state: 'queued' } }),
    getJob: async () => {
      if (++calls === 1) throw new Error('network')
      return { data: { state: 'failed', message: '外部源搜索失败，请稍后重试' } }
    },
  }
  await assert.rejects(
    pollExternalSearch(
      {},
      {
        signal: new AbortController().signal,
        current: () => true,
        onStatus: () => {},
        api,
        wait: async () => {},
      }
    ),
    /请稍后重试/
  )
  assert.equal(calls, 2)
})

test('abort immediately releases the pending polling timer', async () => {
  const controller = new AbortController()
  const waiting = waitForSearchPoll(controller.signal, 60000)
  controller.abort()
  await waiting
})
