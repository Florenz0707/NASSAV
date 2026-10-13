import test from 'node:test'
import assert from 'node:assert/strict'
import { createPlaybackProgress } from '../src/features/playback/lib/playbackProgress.js'
import {
  createProgressDrafts,
  clearPlaybackDrafts,
} from '../src/features/playback/lib/progressDrafts.js'
const turn = () => new Promise((resolve) => setImmediate(resolve))
const saved = {
  version: 1,
  writer_generation: 0,
  ledger_key: 'user-media',
  position_seconds: 30,
  duration_seconds: 100,
  completed: false,
  restore_policy: 'confirm',
}
const row = { session_id: 'session', generation: 1 }
function video() {
  const media = new EventTarget()
  Object.assign(media, {
    currentTime: 0,
    duration: 100,
    ended: false,
    play() {
      this.dispatchEvent(new Event('play'))
      return Promise.resolve()
    },
  })
  return media
}
function setup(overrides = {}) {
  const calls = [],
    changes = []
  let clock = 0,
    version = 1
  const api = {
    progress: async () => ({ data: { ...saved } }),
    claimProgress: async () => ({ data: { ...saved, writer_generation: 1 } }),
    saveProgress: async (_id, body) => {
      calls.push(body)
      return { data: { ...saved, version: ++version, writer_generation: 1 } }
    },
    ...overrides,
  }
  const tracker = createPlaybackProgress({
    api,
    changed: (value) => changes.push(value),
    now: () => clock,
    uuid: () => 'command',
    drafts: createProgressDrafts(null),
  })
  return {
    tracker,
    calls,
    changes,
    tick: (value) => {
      clock = value
    },
  }
}

test('offers compatible position and restores only on explicit choice', async () => {
  const s = setup(),
    v = video()
  await s.tracker.bind(row, v)
  assert.equal(s.changes.at(-1).candidate.position_seconds, 30)
  v.dispatchEvent(new Event('pause'))
  await turn()
  assert.equal(s.calls.length, 0)
  await s.tracker.choose(true)
  await turn()
  assert.equal(v.currentTime, 30)
  assert.equal(s.calls[0].position_seconds, 30)
  await s.tracker.detach()
})

test('throttles timeupdate, saves backward seek and completion', async () => {
  const s = setup(),
    v = video()
  await s.tracker.bind(row, v)
  await s.tracker.choose(false)
  await turn()
  assert.equal(s.calls[0].position_seconds, 0)
  v.currentTime = 60
  s.tick(14000)
  v.dispatchEvent(new Event('timeupdate'))
  await turn()
  assert.equal(s.calls.length, 1)
  s.tick(16000)
  v.dispatchEvent(new Event('timeupdate'))
  await turn()
  v.currentTime = 12
  v.dispatchEvent(new Event('seeked'))
  await turn()
  assert.equal(s.calls.at(-1).position_seconds, 12)
  v.currentTime = 100
  v.ended = true
  v.dispatchEvent(new Event('ended'))
  await turn()
  assert.equal(s.calls.at(-1).completed, true)
  await s.tracker.detach()
})

test('one save in flight merges newer positions using the updated version', async () => {
  let resolve,
    active = 0,
    max = 0
  const s = setup({
      saveProgress: async (_id, body) => {
        active++
        max = Math.max(max, active)
        s.calls.push(body)
        if (s.calls.length === 1)
          await new Promise((r) => {
            resolve = r
          })
        active--
        return { data: { ...saved, writer_generation: 1, version: s.calls.length + 1 } }
      },
    }),
    v = video()
  await s.tracker.bind(row, v)
  await v.play()
  await turn()
  v.currentTime = 25
  v.dispatchEvent(new Event('pause'))
  v.currentTime = 40
  v.dispatchEvent(new Event('seeked'))
  resolve()
  await turn()
  await turn()
  assert.equal(max, 1)
  assert.equal(s.calls[1].position_seconds, 40)
  assert.equal(s.calls[1].expected_version, 2)
  await s.tracker.detach()
})

test('lost response retries identical payload before sending latest position', async () => {
  let failed = false
  const s = setup({
      saveProgress: async (_id, body) => {
        s.calls.push(body)
        if (!failed) {
          failed = true
          throw new Error('lost response')
        }
        return { data: { ...saved, writer_generation: 1, version: s.calls.length } }
      },
    }),
    v = video()
  await s.tracker.bind(row, v)
  await v.play()
  await turn()
  v.currentTime = 50
  v.dispatchEvent(new Event('pause'))
  await turn()
  await turn()
  assert.deepEqual(s.calls[0], s.calls[1])
  assert.equal(s.calls.at(-1).position_seconds, 50)
  await s.tracker.detach()
})

test('writer conflict stops saving without automatically taking ownership back', async () => {
  let claims = 0
  const s = setup({
      claimProgress: async () => {
        claims++
        throw Object.assign(new Error(), { httpStatus: 409 })
      },
    }),
    v = video()
  await s.tracker.bind(row, v)
  await v.play()
  await turn()
  for (let i = 0; i < 3; i++) {
    v.dispatchEvent(new Event('pause'))
    await turn()
  }
  assert.equal(claims, 1)
  assert.equal(s.calls.length, 0)
  assert.match(s.changes.at(-1).message, /失效/)
  await s.tracker.detach()
})

test('leaving captures position and removes subscriptions before player destruction', async () => {
  const leaves = []
  const s = setup({
      saveProgressOnLeave: async (_id, body) => {
        leaves.push(body)
        return { data: { ...saved, writer_generation: 1, version: 3 } }
      },
    }),
    v = video()
  await s.tracker.bind(row, v)
  await v.play()
  await turn()
  v.currentTime = 42
  const leaving = s.tracker.detach(true)
  v.currentTime = 0
  v.dispatchEvent(new Event('pause'))
  await leaving
  assert.equal(leaves[0].position_seconds, 42)
  assert.equal(leaves[0].close_after_save, true)
  assert.equal(leaving.closesSession, true)
})

test('late query cannot overwrite the new resource UI', async () => {
  let resolve
  const s = setup({
    progress: (id) =>
      id === 'old'
        ? new Promise((r) => {
            resolve = r
          })
        : Promise.resolve({ data: { ...saved, position_seconds: 0 } }),
  })
  const old = s.tracker.bind({ ...row, session_id: 'old' }, video())
  await s.tracker.bind(row, video())
  resolve({ data: saved })
  await old
  assert.equal(s.changes.at(-1).candidate, null)
  await s.tracker.detach()
})

test('completed, near-end or incompatible durations do not offer restoration', async () => {
  for (const data of [
    { ...saved, completed: true },
    { ...saved, position_seconds: 99 },
    { ...saved, duration_seconds: 120 },
  ]) {
    const s = setup({ progress: async () => ({ data }) })
    await s.tracker.bind(row, video())
    assert.equal(s.changes.at(-1).candidate, null)
    await s.tracker.detach()
  }
})

test('drafts are bounded, isolated and invalidated by ownership, version or logout', () => {
  let value = '{}'
  const storage = {
    getItem: () => value,
    setItem: (_key, v) => {
      value = v
    },
    removeItem: () => {
      value = '{}'
    },
  }
  const drafts = createProgressDrafts(storage, () => 100),
    snapshot = { ...saved, writer_generation: 1 }
  const body = {
    position_seconds: 50,
    duration_seconds: 100,
    completed: false,
    writer_generation: 1,
    sequence: 2,
    expected_version: 1,
  }
  drafts.put(snapshot, body)
  assert.equal(drafts.get(snapshot).position_seconds, 50)
  assert.equal(drafts.get({ ...snapshot, ledger_key: 'other' }), null)
  assert.equal(drafts.get({ ...snapshot, version: 2 }), null)
  assert.equal(drafts.get({ ...snapshot, writer_generation: 2 }), null)
  drafts.remove(snapshot, { ...body, sequence: 1 })
  assert.ok(drafts.get(snapshot))
  for (let i = 0; i < 30; i++) drafts.put({ ...snapshot, ledger_key: `item-${i}` }, body)
  assert.equal(Object.keys(JSON.parse(value)).length, 20)
  clearPlaybackDrafts(storage)
  assert.equal(drafts.get(snapshot), null)
  value = 'null'
  assert.equal(drafts.get(snapshot), null)
})

test('failed progress read allows playback and preserves the explanation', async () => {
  const s = setup({
      progress: async () => {
        throw new Error('offline')
      },
    }),
    v = video()
  await s.tracker.bind(row, v)
  await v.play()
  await turn()
  assert.equal(s.calls.length, 0)
  assert.match(s.changes.at(-1).message, /本次仍可播放/)
  await s.tracker.detach()
})

test('opening a second device never claims and an explicit transfer uses the latest position', async () => {
  let position = 30,
    claims = 0
  const s = setup({
      progress: async () => ({
        data: {
          ...saved,
          writer_generation: 4,
          writer_active: true,
          is_writer: false,
          position_seconds: position,
        },
      }),
      claimProgress: async (_id, body) => {
        claims++
        assert.equal(body.expected_writer_generation, 4)
        return {
          data: {
            ...saved,
            writer_generation: 5,
            writer_active: true,
            is_writer: true,
            position_seconds: position,
          },
        }
      },
    }),
    v = video()
  v.pause = () => v.dispatchEvent(new Event('pause'))
  await s.tracker.bind(row, v)
  assert.equal(s.changes.at(-1).takeover, true)
  await v.play()
  await turn()
  assert.equal(claims, 0)
  position = 45
  await s.tracker.choose(true)
  await turn()
  assert.equal(claims, 1)
  assert.equal(v.currentTime, 45)
  assert.equal(s.calls.at(-1).position_seconds, 45)
  await s.tracker.detach()
})

test('readonly playback never saves or automatically reclaims the writer', async () => {
  let claims = 0
  const s = setup({
      progress: async () => ({ data: { ...saved, writer_active: true, is_writer: false } }),
      claimProgress: async () => {
        claims++
        return { data: saved }
      },
    }),
    v = video()
  await s.tracker.bind(row, v)
  await s.tracker.playWithoutSaving()
  v.currentTime = 60
  v.dispatchEvent(new Event('seeked'))
  s.tick(20000)
  v.dispatchEvent(new Event('timeupdate'))
  await turn()
  assert.equal(claims, 0)
  assert.equal(s.calls.length, 0)
  assert.equal(s.changes.at(-1).canTakeover, true)
  await s.tracker.detach()
})

test('a transfer conflict requires a new explicit choice instead of automatic stealing', async () => {
  let claims = 0
  const s = setup({
      progress: async () => ({ data: { ...saved, writer_active: true, is_writer: false } }),
      claimProgress: async () => {
        claims++
        throw Object.assign(new Error('race'), { httpStatus: 409 })
      },
    }),
    v = video()
  v.pause = () => {}
  await s.tracker.bind(row, v)
  await s.tracker.choose(true)
  assert.equal(claims, 1)
  assert.equal(s.changes.at(-1).takeover, true)
  v.dispatchEvent(new Event('timeupdate'))
  await turn()
  assert.equal(claims, 1)
  assert.equal(s.calls.length, 0)
  await s.tracker.detach()
})

test('a valid offline draft survives explicit resume when no other device holds the writer', async () => {
  const v = video(),
    changes = []
  const tracker = createPlaybackProgress({
    api: {
      progress: async () => ({ data: saved }),
      claimProgress: async () => ({ data: { ...saved, writer_generation: 1 } }),
      saveProgress: async () => ({ data: { ...saved, writer_generation: 1, version: 2 } }),
    },
    drafts: { get: () => ({ ...saved, position_seconds: 35 }), put: () => {}, remove: () => {} },
    changed: (state) => changes.push(state),
    uuid: () => 'draft-claim',
  })
  await tracker.bind(row, v)
  await tracker.choose(true)
  assert.equal(v.currentTime, 35)
  await tracker.detach()
})
