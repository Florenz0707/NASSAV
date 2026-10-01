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

test('push wakes polling, renders each page and ignores unrelated or stale events', async () => {
  let listener
  let release
  let unsubscribed = false
  const rendered = []
  const partial = { data: { external_results: [{ avid: 'FIRST-001' }] } }
  const final = { data: { external_results: [{ avid: 'FIRST-001' }, { avid: 'NEXT-002' }] } }
  const snapshots = [
    { state: 'running', version: 3, result: partial },
    { state: 'running', version: 2, result: { data: {} } },
    { state: 'succeeded', version: 5, result: final },
  ]
  let calls = 0
  const task = pollExternalSearch(
    {},
    {
      signal: new AbortController().signal,
      current: () => true,
      onStatus: () => {},
      onResult: (result) => rendered.push(result),
      subscribe: (callback) => {
        listener = callback
        return () => {
          unsubscribed = true
        }
      },
      wait: (_signal, listen) =>
        new Promise((resolve) => {
          release = resolve
          listen(resolve)
        }),
      api: {
        submit: async () => ({
          data: { task_id: 'id', token: 'token', state: 'queued', version: 1 },
        }),
        getJob: async () => {
          calls++
          return { data: snapshots.shift() }
        },
      },
    }
  )
  const tick = () => new Promise((resolve) => setImmediate(resolve))
  await tick()
  listener({ task_id: 'other', version: 10 })
  listener({ task_id: 'id', version: 1 })
  await tick()
  assert.equal(calls, 0)
  listener({ task_id: 'id', version: 3 })
  await tick()
  assert.deepEqual(rendered, [partial])
  release() // HTTP fallback gets an older snapshot: do not regress visible cards.
  await tick()
  assert.deepEqual(rendered, [partial])
  listener({ task_id: 'id', version: 5 })
  assert.deepEqual(await task, final)
  assert.deepEqual(rendered, [partial, final])
  assert.equal(unsubscribed, true)
})

test('notification during a snapshot request triggers immediate follow-up without a poll delay', async () => {
  let listener
  let releaseHttp
  let waits = 0
  let calls = 0
  const final = { data: { external_results: [] } }
  const task = pollExternalSearch(
    {},
    {
      signal: new AbortController().signal,
      current: () => true,
      onStatus: () => {},
      subscribe: (callback) => {
        listener = callback
        return () => {}
      },
      wait: async () => {
        waits++
      },
      api: {
        submit: async () => ({ data: { task_id: 'id', state: 'queued', version: 1 } }),
        getJob: () =>
          ++calls === 1
            ? new Promise((resolve) => {
                releaseHttp = resolve
              })
            : Promise.resolve({ data: { state: 'succeeded', version: 4, result: final } }),
      },
    }
  )
  await new Promise((resolve) => setImmediate(resolve))
  listener({ task_id: 'id', version: 4 })
  releaseHttp({ data: { state: 'running', version: 2 } })
  assert.deepEqual(await task, final)
  assert.equal(waits, 1)
  assert.equal(calls, 2)
})

test('failed task publishes preserved partial cards before rejecting and removes subscription', async () => {
  const partial = {
    data: { external_meta: { partial: true }, external_results: [{ avid: 'OK-001' }] },
  }
  const rendered = []
  let unsubscribed = false
  await assert.rejects(
    pollExternalSearch(
      {},
      {
        signal: new AbortController().signal,
        current: () => true,
        onStatus: () => {},
        onResult: (result) => rendered.push(result),
        subscribe: () => () => {
          unsubscribed = true
        },
        api: { submit: async () => ({ data: { state: 'failed', version: 5, result: partial } }) },
      }
    ),
    /搜索失败/
  )
  assert.deepEqual(rendered, [partial])
  assert.equal(unsubscribed, true)
})

test('a push releases and cleans a pending timer immediately', async () => {
  let wake
  let cleaned = false
  await Promise.all([
    waitForSearchPoll(new AbortController().signal, 60000, (finish) => {
      wake = finish
      return () => {
        cleaned = true
      }
    }),
    Promise.resolve().then(() => wake()),
  ])
  assert.equal(cleaned, true)
})
