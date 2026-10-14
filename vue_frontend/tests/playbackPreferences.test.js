import test from 'node:test'
import assert from 'node:assert/strict'
import {
  bindPlaybackPreferences,
  playbackMode,
} from '../src/features/playback/lib/playbackPreferences.js'
const tick = () => new Promise((resolve) => setTimeout(resolve, 10))
const defaults = { volume: 0.8, muted: false, rate: 1 }
function video() {
  return Object.assign(new EventTarget(), defaults, { playbackRate: 1 })
}

test('initial media events do not save defaults; user changes are serialized and coalesced', async () => {
  const media = video(),
    calls = []
  let release
  const dispose = bindPlaybackPreferences(media, {
    preferences: defaults,
    delay: 0,
    save: (patch) => {
      calls.push(patch)
      return calls.length === 1
        ? new Promise((resolve) => {
            release = resolve
          })
        : Promise.resolve()
    },
  })
  media.dispatchEvent(new Event('volumechange'))
  await tick()
  assert.equal(calls.length, 0)
  media.volume = 0.4
  media.dispatchEvent(new Event('volumechange'))
  await tick()
  media.volume = 0.6
  media.playbackRate = 1.5
  media.dispatchEvent(new Event('ratechange'))
  await tick()
  assert.equal(calls.length, 1)
  release()
  await tick()
  assert.deepEqual(calls, [{ volume: 0.4 }, { volume: 0.6, rate: 1.5 }])
  dispose()
  media.volume = 1
  media.dispatchEvent(new Event('volumechange'))
  await tick()
  assert.equal(calls.length, 2)
})

test('invalidated attachment cannot save and playback modes keep explicit intent', async () => {
  const media = video(),
    calls = []
  let current = true
  const dispose = bindPlaybackPreferences(media, {
    preferences: defaults,
    delay: 0,
    current: () => current,
    save: (patch) => calls.push(patch),
  })
  media.volume = 0.4
  media.dispatchEvent(new Event('volumechange'))
  current = false
  await tick()
  dispose()
  assert.equal(calls.length, 0)
  assert.equal(playbackMode('source', 'local', true), 'source')
  assert.equal(playbackMode('local', 'source', true), 'local')
  assert.equal(playbackMode('auto', 'auto', true), 'local')
  assert.equal(playbackMode('auto', 'auto', false), 'source')
})

test('teardown drains the latest real change after an in-flight write', async () => {
  const media = video(),
    calls = []
  let release,
    current = true
  const dispose = bindPlaybackPreferences(media, {
    preferences: defaults,
    delay: 0,
    current: () => current,
    save: (patch) => {
      calls.push(patch)
      return calls.length === 1
        ? new Promise((resolve) => {
            release = resolve
          })
        : Promise.resolve()
    },
  })
  media.volume = 0.4
  media.dispatchEvent(new Event('volumechange'))
  await tick()
  media.volume = 0.6
  media.dispatchEvent(new Event('volumechange'))
  dispose()
  current = false
  release()
  await tick()
  assert.deepEqual(calls, [{ volume: 0.4 }, { volume: 0.6 }])
})
