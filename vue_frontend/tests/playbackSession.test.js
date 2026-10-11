import test from 'node:test'
import assert from 'node:assert/strict'
import { createPlaybackSession } from '../src/features/playback/lib/playbackSession.js'
const deferred = () => {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}
const row = (id, version = 1, state = 'queued') => ({ session_id: id, version, state })

test('closing while submitting fences the late reply and closes its owned session', async () => {
  const pending = deferred(),
    changes = [],
    closed = []
  const session = createPlaybackSession({
    api: {
      submit: () => pending.promise,
      close: async (...args) => closed.push(args),
      status: async () => {
        throw Error('must not poll old session')
      },
    },
    changed: (value) => changes.push(value),
    uuid: () => 'command',
  })
  const start = session.start('DEMO-1')
  await new Promise((resolve) => setImmediate(resolve))
  await session.dispose()
  pending.resolve({ data: row('late') })
  await start
  assert.equal(closed.length, 1)
  assert.equal(closed[0][0], 'late')
  assert.equal(changes.length, 1)
})

test('old polling replies cannot overwrite a new resource session', async () => {
  const pending = deferred(),
    changes = [],
    closed = []
  const session = createPlaybackSession({
    api: {
      submit: async (avid) => ({ data: row(avid) }),
      close: async (id) => closed.push(id),
      status: async (id) => (id === 'OLD' ? pending.promise : { data: row('NEW', 3, 'ready') }),
    },
    changed: (value) => changes.push(value),
  })
  const old = session.start('OLD')
  await new Promise((resolve) => setImmediate(resolve))
  await session.start('NEW')
  pending.resolve({ data: { ...row('OLD', 3, 'ready'), manifest_url: 'old' } })
  await old
  assert.equal(changes.at(-1).session_id, 'NEW')
  assert.deepEqual(closed, ['OLD'])
  await session.dispose()
})

test('close retries a version conflict with one idempotency key', async () => {
  let calls = 0
  const commands = []
  const session = createPlaybackSession({
    api: {
      submit: async () => ({ data: row('session') }),
      status: async () => ({ data: row('session', 3, 'ready') }),
      close: async (_id, version, command) => {
        commands.push(command)
        if (++calls === 1) throw { httpStatus: 409 }
        assert.equal(version, 3)
      },
    },
    changed: () => {},
  })
  await session.start('DEMO')
  await session.stop()
  assert.equal(calls, 2)
  assert.equal(commands[0], commands[1])
})
