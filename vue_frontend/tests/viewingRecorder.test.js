import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createViewingRecorder } from '../src/features/playback/lib/viewingRecorder.js'
const tick = () => new Promise((resolve) => setImmediate(resolve))
function video() {
  return new EventTarget()
}
test('only real playing records, repeated events dedupe independently of progress writing', async () => {
  const v = video(),
    calls = []
  const recorder = createViewingRecorder({ record: async (...args) => calls.push(args) })
  recorder.bind({ session_id: 'one', generation: 1 }, v)
  v.dispatchEvent(new Event('loadedmetadata'))
  v.dispatchEvent(new Event('play'))
  assert.equal(calls.length, 0)
  v.dispatchEvent(new Event('playing'))
  v.dispatchEvent(new Event('playing'))
  await tick()
  v.dispatchEvent(new Event('playing'))
  assert.deepEqual(calls, [['one', 1, 1]])
  recorder.detach()
  v.dispatchEvent(new Event('playing'))
  assert.equal(calls.length, 1)
})
test('failures can retry and old responses cannot alter the new player', async () => {
  const a = video(),
    b = video(),
    messages = []
  let rejectOld,
    count = 0
  const recorder = createViewingRecorder({
    changed: (m) => messages.push(m),
    record: () => {
      count++
      return count === 1
        ? new Promise((_, reject) => {
            rejectOld = reject
          })
        : Promise.resolve()
    },
  })
  recorder.bind({ session_id: 'old', generation: 1 }, a)
  a.dispatchEvent(new Event('play'))
  a.dispatchEvent(new Event('playing'))
  recorder.bind({ session_id: 'new', generation: 2 }, b)
  rejectOld(new Error('old failure'))
  await tick()
  assert.equal(messages.at(-1), '')
  await recorder.retry()
  assert.equal(count, 1)
  b.dispatchEvent(new Event('play'))
  b.dispatchEvent(new Event('playing'))
  await tick()
  assert.equal(count, 2)
})
test('lost recording response retries on explicit choice with same session identity', async () => {
  const v = video(),
    calls = [],
    messages = []
  const recorder = createViewingRecorder({
    changed: (m) => messages.push(m),
    record: async (...args) => {
      calls.push(args)
      if (calls.length === 1) throw new Error('lost')
    },
  })
  recorder.bind({ session_id: 'one', generation: 3 }, v)
  v.dispatchEvent(new Event('play'))
  v.dispatchEvent(new Event('playing'))
  await tick()
  assert.match(messages.at(-1), /重试/)
  await recorder.retry()
  assert.deepEqual(calls, [
    ['one', 3, 1],
    ['one', 3, 1],
  ])
  assert.equal(messages.at(-1), '')
})

test('resume starts a new episode, buffering does not, refresh retains monotonic sequence', async () => {
  const v = video(),
    calls = []
  const recorder = createViewingRecorder({ record: async (...args) => calls.push(args) })
  recorder.bind({ session_id: 'one', generation: 1, history_sequence: 4 }, v)
  v.dispatchEvent(new Event('play'))
  v.dispatchEvent(new Event('playing'))
  await tick()
  v.dispatchEvent(new Event('playing'))
  await tick()
  v.dispatchEvent(new Event('pause'))
  v.dispatchEvent(new Event('play'))
  v.dispatchEvent(new Event('playing'))
  await tick()
  recorder.bind({ session_id: 'one', generation: 2, history_sequence: 4 }, v)
  v.dispatchEvent(new Event('play'))
  v.dispatchEvent(new Event('playing'))
  await tick()
  assert.deepEqual(calls, [
    ['one', 1, 5],
    ['one', 1, 6],
    ['one', 2, 7],
  ])
})
