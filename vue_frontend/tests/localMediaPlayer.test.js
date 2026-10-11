import test from 'node:test'
import assert from 'node:assert/strict'
import { attachPlayer } from '../src/features/playback/lib/mediaPlayer.js'

function videoFixture() {
  const events = new Map()
  return {
    events,
    duration: 90,
    currentTime: 0,
    paused: true,
    addEventListener: (name, handler) => events.set(name, handler),
    removeEventListener: (name) => events.delete(name),
    pause() {
      this.paused = true
    },
    play() {
      this.paused = false
      return Promise.resolve()
    },
    removeAttribute(name) {
      delete this[name]
    },
    load() {
      this.loaded = true
    },
  }
}

test('MP4 uses the native element and releases its listeners and source', async () => {
  const video = videoFixture(),
    errors = []
  const dispose = await attachPlayer(video, '/nassav/api/playback-sessions/local/file', {
    mediaType: 'mp4',
    position: 12,
    failed: (message) => errors.push(message),
  })
  assert.equal(video.src, '/nassav/api/playback-sessions/local/file')
  video.events.get('loadedmetadata')()
  assert.equal(video.currentTime, 12)
  video.events.get('error')()
  assert.equal(errors.length, 1)
  dispose()
  dispose()
  assert.equal(video.src, undefined)
  assert.equal(video.events.size, 0)
  assert.equal(video.paused, true)
})

test('a superseded local attach does not bind media or leak listeners', async () => {
  const video = videoFixture()
  await attachPlayer(video, '/nassav/api/playback-sessions/local/file', {
    mediaType: 'mp4',
    current: () => false,
    failed: () => {},
  })
  assert.equal(video.src, undefined)
  assert.equal(video.events.size, 0)
})
