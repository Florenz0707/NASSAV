import test from 'node:test'
import assert from 'node:assert/strict'
import { createLibraryCommands } from '../src/features/library/lib/libraryCommands.js'

const entry = (version = 2) => ({
  entry_id: 'entry-a',
  entry_version: version,
  membership_state: 'active',
  is_in_my_library: true,
})
const absent = () => ({
  entry_id: null,
  entry_version: null,
  membership_state: null,
  is_in_my_library: false,
})
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const snapshot = (action = 'add') => ({
  operation_id: 'operation-a',
  avid: 'AV-1',
  action,
  version: 1,
})
function setup(api, held = absent()) {
  let current = held,
    reads = 0,
    serial = 0
  const accepted = [],
    changes = []
  const memberships = {
    errors: new Map(),
    load: async () => {
      reads++
    },
    get: () => current,
  }
  const core = createLibraryCommands(api, {
    memberships,
    acceptOperation: (item) => accepted.push(item),
    changed: (...args) => changes.push(args),
    requestId: () => `request-${++serial}`,
  })
  core.reset('login-a')
  return {
    ...core,
    memberships,
    accepted,
    changes,
    reads: () => reads,
    changeEntry: (next) => {
      current = next
    },
  }
}

test('duplicate submissions share a command; public and personal are explicit and do not use legacy endpoints', async () => {
  const pending = deferred(),
    bodies = []
  const commands = setup({
    addEntry: (body) => {
      bodies.push(body)
      return pending.promise
    },
  })
  const first = commands.execute('add', ' av-1 ', { source: 'Jable', credential_mode: 'personal' })
  const duplicate = commands.execute('add', 'AV-1', {
    source: 'jable',
    credential_mode: 'personal',
  })
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(bodies.length, 1)
  assert.equal(bodies[0].source, 'jable')
  assert.equal(bodies[0].credential_mode, 'personal')
  assert.equal(bodies[0].expected_entry_version, undefined)
  pending.resolve({ code: 202, data: { operation: snapshot() } })
  await Promise.all([first, duplicate])
  assert.equal(commands.accepted.length, 1)
  assert.deepEqual(commands.changes, [['AV-1', 'add']])
  await assert.rejects(commands.execute('add', 'AV-1', { source: 'any' }), /明确来源/)
})

test('lost release response retries the original entry UUID, CAS and command UUID even after membership disappears', async () => {
  const bodies = []
  let calls = 0
  const commands = setup(
    {
      releaseEntry: async (id, body) => {
        bodies.push([id, body])
        if (++calls === 1) throw new Error('outcome unknown')
        return { code: 200, data: { released: true } }
      },
    },
    entry()
  )
  await assert.rejects(commands.execute('release', 'AV-1'), /outcome unknown/)
  commands.changeEntry(absent())
  await commands.execute('release', 'AV-1')
  assert.equal(commands.reads(), 1)
  assert.deepEqual(bodies[0], bodies[1])
  assert.deepEqual(bodies[1], ['entry-a', { expected_version: 2, request_id: 'request-1' }])
})

test('lost add response retries identical body rather than deriving a new intent from pending membership', async () => {
  const bodies = []
  let calls = 0
  const commands = setup({
    addEntry: async (body) => {
      bodies.push(body)
      if (++calls === 1) throw new Error('timeout')
      return { data: { operation: snapshot() } }
    },
  })
  await assert.rejects(commands.execute('add', 'AV-1', { source: 'jable' }), /timeout/)
  commands.changeEntry({ ...entry(4), membership_state: 'pending' })
  await commands.execute('add', 'AV-1', { source: 'jable' })
  assert.equal(commands.reads(), 1)
  assert.deepEqual(bodies[0], bodies[1])
})

test('definitive membership conflict is tagged, retains no false success and obtains fresh CAS only on a new explicit action', async () => {
  const bodies = []
  let calls = 0
  const commands = setup(
    {
      submitEntryOperation: async (id, body) => {
        bodies.push(body)
        if (++calls === 1) throw { code: 409, message: 'membership_version_conflict' }
        return { data: snapshot('refresh') }
      },
    },
    entry()
  )
  await assert.rejects(
    commands.execute('refresh', 'AV-1', { source: 'jable' }),
    (error) => error.sharedLibrary === true && error.code === 409
  )
  assert.equal(commands.accepted.length, 0)
  commands.changeEntry(entry(5))
  await commands.execute('refresh', 'AV-1', { source: 'jable' })
  assert.equal(bodies[1].expected_entry_version, 5)
  assert.notEqual(bodies[0].request_id, bodies[1].request_id)
})

test('identity change during status lookup prevents the old mutation; late writes cannot publish to new UI', async () => {
  let calls = 0
  const waiting = deferred()
  const commands = setup({
    addEntry: async () => {
      calls++
      return { data: { operation: snapshot() } }
    },
  })
  commands.memberships.load = () => waiting.promise
  const old = commands.execute('add', 'AV-1', { source: 'jable' })
  await Promise.resolve()
  commands.reset('b')
  waiting.resolve()
  await assert.rejects(old, (error) => error.code === 'session_changed')
  assert.equal(calls, 0)
  const response = deferred()
  const next = setup({ addEntry: () => response.promise })
  const pending = next.execute('add', 'AV-1', { source: 'jable' })
  await new Promise((resolve) => setImmediate(resolve))
  next.reset('b')
  response.resolve({ data: { operation: snapshot() } })
  await assert.rejects(pending, (error) => error.code === 'session_changed')
  assert.equal(next.accepted.length, 0)
  assert.equal(next.changes.length, 0)
})

test('unknown membership and pending refresh cannot send mutations; batches preserve partial failures', async () => {
  let calls = 0
  const commands = setup(
    {
      releaseEntry: async () => {
        if (++calls === 2) throw new Error('storage unavailable')
        return { code: 200, data: {} }
      },
    },
    entry()
  )
  const results = await commands.batch('release', ['AV-1', 'AV-2', 'AV-1'])
  assert.deepEqual(
    results.map((item) => [item.avid, item.code]),
    [
      ['AV-1', 200],
      ['AV-2', 500],
    ]
  )
  assert.equal(calls, 2)
  await assert.rejects(
    commands.batch(
      'release',
      Array.from({ length: 101 }, (_, index) => `AV-${index}`)
    ),
    /100/
  )
  commands.changeEntry({ ...entry(), membership_state: 'pending' })
  await assert.rejects(commands.execute('refresh', 'AV-1', { source: 'jable' }), /资源暂不可用/)
  commands.memberships.errors.set('AV-3', 'status offline')
  await assert.rejects(commands.execute('release', 'AV-3'), /status offline/)
})

test('a stale rendered holding cannot remove a newly re-added relation of the same AVID', async () => {
  let deletes = 0
  const commands = setup(
    {
      releaseEntry: async () => {
        deletes++
        return { code: 200, data: {} }
      },
    },
    { ...entry(5), entry_id: 'new-entry' }
  )
  await assert.rejects(
    commands.execute('release', 'AV-1', { membership: entry(2) }),
    (error) => error.httpStatus === 409 && error.code === 'membership_version_conflict'
  )
  assert.equal(deletes, 0)
  await commands.execute('release', 'AV-1', { membership: { ...entry(5), entry_id: 'new-entry' } })
  assert.equal(deletes, 1)
})
