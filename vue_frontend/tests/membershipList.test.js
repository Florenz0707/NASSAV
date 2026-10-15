import test from 'node:test'
import assert from 'node:assert/strict'
import { createMembershipList } from '../src/features/library/lib/membershipList.js'
import { libraryBatchOutcome } from '../src/features/library/lib/batchResults.js'

const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const result = (avid) => ({
  data: [{ avid }],
  pagination: { total: 1, page: 1, pages: 1, page_size: 20 },
})
test('membership query rejects stale errors/results and cannot repopulate a closed dialog', async () => {
  const requests = []
  const list = createMembershipList(() => {
    const pending = deferred()
    requests.push(pending)
    return pending.promise
  })
  const old = list.load({ search: 'old' }),
    current = list.load({ search: 'new' })
  requests[0].reject(new Error('old private error'))
  await old
  assert.equal(list.loading.value, true)
  assert.equal(list.error.value, '')
  requests[1].resolve(result('NEW'))
  await current
  assert.equal(list.rows.value[0].avid, 'NEW')
  const late = list.load({})
  list.dispose()
  requests[2].resolve(result('LATE'))
  await late
  assert.deepEqual(list.rows.value, [])
})
test('shared batch results retain missing failures and ignore unrequested success counts', () => {
  const outcome = libraryBatchOutcome(
    {
      data: {
        results: [
          { avid: 'OK', code: 202 },
          { avid: 'FOREIGN', code: 200 },
          { avid: 'BAD', code: 409 },
        ],
      },
    },
    ['OK', 'BAD', 'MISSING', 'OK']
  )
  assert.deepEqual(outcome.accepted, ['OK'])
  assert.deepEqual(
    outcome.failed.map((item) => item.avid),
    ['BAD', 'MISSING']
  )
})
