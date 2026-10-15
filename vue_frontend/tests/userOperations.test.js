import assert from 'node:assert/strict'
import test from 'node:test'
import { createOperationTracking } from '../src/features/tasks/composables/operationTracking.js'
import { buildOperationDetails } from '../src/features/tasks/lib/operationDetails.js'

const item = (changes = {}) => ({
  operation_id: 'owned',
  avid: 'AV-1',
  kind: 'scrape',
  action: 'add',
  state: 'running',
  stage: 'metadata',
  version: 2,
  allowed_actions: ['cancel'],
  ...changes,
})
const response = (data) => ({ data })
const list = (data = []) => ({ data, pagination: { total: data.length, pages: 1 } })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const create = (api) => {
  const tracker = createOperationTracking(api, {
    storage: () => null,
    requestId: () => 'request-id',
  })
  tracker.reset('login-a')
  return tracker
}

test('own operations keep raw identity/version, distinct from shared jobs and attempts', () => {
  const tracker = create({})
  tracker.apply(item())
  tracker.apply(item({ version: 3, state: 'succeeded', allowed_actions: [] }))
  tracker.apply(item({ version: 2, state: 'running' }))
  assert.equal(tracker.visible.value[0].state, 'succeeded')
  const [detail] = buildOperationDetails(tracker.visible.value)
  assert.equal(detail.operationId, 'owned')
  assert.equal(detail.jobId, undefined)
  assert.equal(detail.id, 'operation:owned')
  assert.equal(detail.hasResource, false)
  assert.deepEqual(detail.allowedActions, [])
})

test('cancel only accepted own actions; partial errors retain original UUID for retry without optimistic stop', async () => {
  const pending = deferred(),
    bodies = []
  let calls = 0
  const tracker = create({
    cancelOperation: (id, body) => {
      bodies.push([id, body])
      if (++calls === 1) return pending.promise
      return response(item({ version: 3, state: 'cancelled', allowed_actions: [] }))
    },
  })
  tracker.apply(item())
  tracker.apply(item({ operation_id: 'ended', state: 'failed', allowed_actions: [] }))
  const first = tracker.cancel(['owned', 'owned', 'ended', 'foreign'])
  assert.equal(tracker.busy.value.has('owned'), true)
  assert.equal(tracker.visible.value[0].state, 'running')
  assert.deepEqual(await tracker.cancel(['owned']), [])
  pending.reject(new Error('transport unknown'))
  assert.deepEqual(await first, [{ operation_id: 'owned', ok: false }])
  assert.equal(tracker.busy.value.size, 0)
  await tracker.cancel(['owned'])
  assert.deepEqual(bodies, [
    ['owned', { expected_version: 2, request_id: 'request-id' }],
    ['owned', { expected_version: 2, request_id: 'request-id' }],
  ])
  assert.equal(tracker.visible.value[0].state, 'cancelled')
})

test('CAS conflict refreshes own snapshot but never automatically retries cancellation', async () => {
  let cancels = 0
  const tracker = create({
    cancelOperation: async () => {
      cancels++
      throw { code: 409, message: 'version conflict' }
    },
    getOperation: async () =>
      response(item({ version: 4, state: 'succeeded', allowed_actions: [] })),
  })
  tracker.apply(item())
  await tracker.cancel(['owned'])
  assert.equal(cancels, 1)
  assert.equal(tracker.visible.value[0].state, 'succeeded')
  assert.match(tracker.error.value, /version conflict/)
})

test('old login cancellation completion cannot restore snapshots, busy flags or errors', async () => {
  const pending = deferred()
  const tracker = create({ cancelOperation: () => pending.promise })
  tracker.apply(item())
  const old = tracker.cancel(['owned'])
  tracker.reset('login-b')
  pending.resolve(response(item({ version: 3, state: 'cancelled' })))
  await old
  assert.equal(tracker.operations.value.size, 0)
  assert.equal(tracker.busy.value.size, 0)
  assert.equal(tracker.error.value, '')
})

test('sorting and owner changes reject stale list responses and unknown result identities', async () => {
  const first = deferred(),
    second = deferred()
  let calls = 0
  const tracker = create({
    listOperations: () => (++calls === 1 ? first : second).promise,
    getOperation: async () => response(item({ operation_id: 'wrong' })),
  })
  const old = tracker.load()
  const current = tracker.setOrdering('-updated_at')
  second.resolve(list([item({ operation_id: 'new' })]))
  await current
  first.resolve(list([item({ operation_id: 'old' })]))
  await old
  assert.deepEqual(
    tracker.visible.value.map((row) => row.operation_id),
    ['new']
  )
  await tracker.refresh('expected')
  assert.equal(tracker.operations.value.has('wrong'), false)
  tracker.reset('b')
  assert.equal(tracker.total.value, 0)
})

test('websocket hint newer than in-flight response causes an authoritative follow-up read', async () => {
  const pending = deferred()
  let calls = 0
  const tracker = create({
    getOperation: () => (++calls === 1 ? pending.promise : response(item({ version: 4 }))),
  })
  tracker.apply(item())
  const first = tracker.refresh('owned')
  await Promise.resolve()
  tracker.hint({ operation_id: 'owned', version: 4 })
  pending.resolve(response(item({ version: 3 })))
  await first
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(calls, 2)
  assert.equal(tracker.visible.value[0].version, 4)
  tracker.hide(['owned'])
  tracker.hint({ operation_id: 'owned', version: 5 })
  assert.equal(tracker.visible.value.length, 0)
  assert.equal(calls, 2)
})
