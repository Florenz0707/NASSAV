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

test('refresh is single flight, remains one-shot and changes generation', async () => {
  let commands = 0,
    version = 3,
    generation = 1
  const changes = []
  const session = createPlaybackSession({
    api: {
      submit: async () => ({ data: row('session') }),
      status: async () => ({ data: { ...row('session', version, 'ready'), generation } }),
      refresh: async () => {
        commands++
        generation++
        version += 2
        return { data: { ...row('session', version, 'queued'), generation, refresh_count: 1 } }
      },
      close: async () => {},
    },
    changed: (value) => changes.push(value),
  })
  await session.start('DEMO')
  await Promise.all([session.refresh(), session.refresh()])
  assert.equal(commands, 1)
  assert.equal(changes.at(-1).generation, 2)
  assert.equal(await session.refresh(), false)
  await session.dispose()
})

test('local mode sends its mode, uses the MP4 snapshot and never refreshes a source', async () => {
  const submitted = [],
    changes = []
  const local = {
    ...row('local', 1, 'ready'),
    mode: 'local',
    media_type: 'mp4',
    media_url: '/file',
  }
  const session = createPlaybackSession({
    api: {
      submit: async (...args) => {
        submitted.push(args)
        return { data: local }
      },
      status: async () => ({ data: local }),
      refresh: () => {
        throw Error('must not fetch a source')
      },
      close: async () => {},
    },
    changed: (value) => changes.push(value),
    uuid: () => 'request',
  })
  await session.start('DEMO', 'local')
  assert.deepEqual(submitted, [['DEMO', 'request', 'local']])
  assert.equal(changes.at(-1).media_url, '/file')
  assert.equal(await session.refresh(), false)
  await session.dispose()
})

test('switching modes for the same AVID fences the late old mode', async () => {
  const pending = deferred(),
    changes = [],
    closed = []
  const session = createPlaybackSession({
    api: {
      submit: async (_avid, _id, mode) => ({ data: row(mode) }),
      status: async (id) =>
        id === 'local' ? pending.promise : { data: row('source', 2, 'ready') },
      close: async (id) => closed.push(id),
    },
    changed: (value) => changes.push(value),
  })
  const first = session.start('DEMO', 'local')
  await new Promise((resolve) => setImmediate(resolve))
  await session.start('DEMO', 'source')
  pending.resolve({ data: { ...row('local', 3, 'ready'), media_url: '/old-local' } })
  await first
  assert.equal(changes.at(-1).session_id, 'source')
  assert.deepEqual(closed, ['local'])
  await session.dispose()
})

test('a missing local file reports an error without falling back to source', async () => {
  const modes = [],
    changes = []
  const session = createPlaybackSession({
    api: {
      submit: async (_avid, _id, mode) => {
        modes.push(mode)
        throw { httpStatus: 404, message: 'local_video_not_found' }
      },
    },
    changed: (value) => changes.push(value),
  })
  await session.start('DEMO', 'local')
  assert.deepEqual(modes, ['local'])
  assert.equal(changes.at(-1).message, '已下载视频不存在，请检查文件或重新下载')
  await session.dispose()
})
