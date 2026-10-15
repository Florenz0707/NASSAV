import test from 'node:test'
import assert from 'node:assert/strict'
import { createMembershipLookup } from '../src/features/library/lib/membershipLookup.js'

test('reset before transport starts suppresses the old login request entirely', async () => {
  let calls = 0
  const lookup = createMembershipLookup(async () => {
    calls++
    return { data: [] }
  })
  lookup.reset('a')
  const old = lookup.load(['A-1'])
  lookup.reset('b')
  await old
  assert.equal(calls, 0)
  assert.equal(lookup.rows.value.size, 0)
})

const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const status = (avid, owned = false, version = 1) => ({
  avid,
  is_in_my_library: owned,
  is_available: owned,
  entry_id: owned ? `entry-${avid}` : null,
  entry_version: owned ? version : null,
  membership_state: owned ? 'active' : null,
})
const reply = (avids) => ({ data: avids.map((avid) => status(avid)) })

test('membership lookup canonicalizes, deduplicates, shares pending requests and expires cache', async () => {
  let time = 0,
    calls = 0
  const pending = deferred()
  const lookup = createMembershipLookup(
    () => {
      calls++
      return pending.promise
    },
    { now: () => time, ttl: 30 }
  )
  await lookup.load(['A-1'])
  assert.equal(calls, 0)
  lookup.reset('login-a')
  const first = lookup.load([' a-1 ', 'A-1'])
  const second = lookup.load(['A-1'])
  await Promise.resolve()
  assert.equal(calls, 1)
  assert.equal(lookup.loading.value.has('A-1'), true)
  pending.resolve(reply(['A-1']))
  await Promise.all([first, second])
  assert.equal(lookup.get('a-1').is_in_my_library, false)
  assert.equal(lookup.loading.value.size, 0)
  await lookup.load(['A-1'])
  assert.equal(calls, 1)
  time = 31
  await lookup.load(['A-1'])
  assert.equal(calls, 2)
  const revision = lookup.revision.value
  lookup.invalidate()
  assert.equal(lookup.revision.value, revision + 1)
  assert.equal(lookup.get('A-1'), null)
})

test('old login results, errors and cleanup cannot overwrite the new login', async () => {
  const first = deferred(),
    second = deferred()
  let calls = 0
  const lookup = createMembershipLookup(() => (++calls === 1 ? first : second).promise)
  lookup.reset('a')
  const old = lookup.load(['A-1'])
  await Promise.resolve()
  lookup.reset('b')
  const current = lookup.load(['A-1'])
  await Promise.resolve()
  first.reject(new Error('private old error'))
  await old
  assert.equal(lookup.errors.value.size, 0)
  assert.equal(lookup.loading.value.has('A-1'), true)
  second.resolve({ data: [status('A-1', true)] })
  await current
  assert.equal(lookup.get('A-1').entry_version, 1)
  lookup.reset('')
  assert.equal(lookup.rows.value.size, 0)
})

test('overlapping batches publish only the latest request for each resource', async () => {
  const first = deferred(),
    second = deferred()
  let calls = 0
  const lookup = createMembershipLookup(() => (++calls === 1 ? first : second).promise)
  lookup.reset('a')
  const old = lookup.load(['A-1', 'B-1'])
  await Promise.resolve()
  const current = lookup.load(['A-1'], { force: true })
  await Promise.resolve()
  second.resolve({ data: [status('A-1', true, 2)] })
  await current
  first.resolve({ data: [status('A-1', true, 1), status('B-1')] })
  await old
  assert.equal(lookup.get('A-1').entry_version, 2)
  assert.equal(lookup.get('B-1').is_in_my_library, false)
  assert.equal(lookup.loading.value.size, 0)
})

test('invalid or incomplete responses publish no partial membership truth', async () => {
  for (const data of [
    [status('A-1')],
    [status('A-1'), status('UNKNOWN')],
    [status('A-1'), status('A-1')],
    [status('A-1'), { ...status('B-1', true), entry_version: 0 }],
  ]) {
    const lookup = createMembershipLookup(async () => ({ data }))
    lookup.reset('a')
    await lookup.load(['A-1', 'B-1'])
    assert.equal(lookup.rows.value.size, 0)
    assert.equal(lookup.errors.value.size, 2)
    assert.equal(lookup.loading.value.size, 0)
  }
})

test('synchronous transport failures release pending batches and can be retried', async () => {
  let calls = 0
  const lookup = createMembershipLookup((avids) => {
    if (++calls === 1) throw new Error('offline')
    return reply(avids)
  })
  lookup.reset('a')
  await lookup.load(['A-1'])
  assert.equal(lookup.errors.value.get('A-1'), 'offline')
  assert.equal(lookup.loading.value.size, 0)
  await lookup.load(['A-1'])
  assert.equal(lookup.errors.value.size, 0)
  assert.equal(lookup.get('A-1').is_in_my_library, false)
})

test('large lists use sequential bounded batches and a bounded result cache', async () => {
  const sizes = []
  let active = 0
  const lookup = createMembershipLookup(
    async (avids) => {
      assert.equal(active++, 0)
      sizes.push(avids.length)
      await Promise.resolve()
      active--
      return reply(avids)
    },
    { limit: 150 }
  )
  lookup.reset('a')
  await lookup.load(Array.from({ length: 205 }, (_, index) => `A-${index}`))
  assert.deepEqual(sizes, [100, 100, 5])
  assert.equal(lookup.rows.value.size, 150)
  assert.equal(lookup.get('A-0'), null)
  assert.equal(lookup.get('A-204').is_in_my_library, false)
})
