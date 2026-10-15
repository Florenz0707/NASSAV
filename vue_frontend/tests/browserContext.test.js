import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import api, {
  setBrowserContext,
  browserContextHeaders,
  contextualImageUrl,
  onBrowserContextChanged,
  invalidateSessionRequests,
} from '../src/api/client.js'
import { resourceApi } from '../src/api/resources.js'
import { actorApi } from '../src/api/catalog.js'
import { playbackApi } from '../src/api/playback.js'

test('JSON requests and generic image URLs carry the current browser precondition', async () => {
  const original = api.defaults.adapter
  const calls = []
  api.defaults.adapter = async (config) => {
    calls.push(config)
    return { status: 200, config, headers: {}, data: { code: 200, data: {} } }
  }
  try {
    setBrowserContext('current-context')
    await api.put('/setting', { color_mode: 'light' })
    assert.equal(calls[0].headers.get('X-NASSAV-Context'), 'current-context')
    assert.deepEqual(browserContextHeaders(), { 'X-NASSAV-Context': 'current-context' })
    assert.match(resourceApi.getCoverUrl('ABC-001', 'medium'), /&_context=current-context$/)
    assert.match(actorApi.getAvatarUrl(1), /\?_context=current-context$/)
    assert.equal(
      contextualImageUrl('/nassav/api/image?size=small#part'),
      '/nassav/api/image?size=small&_context=current-context#part'
    )
    setBrowserContext()
    assert.equal(resourceApi.getCoverUrl('ABC-001'), '/nassav/api/resource/cover?avid=ABC-001')
  } finally {
    api.defaults.adapter = original
    setBrowserContext()
  }
})

test('context conflict notifies recheck once and never automatically replays writes; stale conflicts are ignored', async () => {
  let notifications = 0,
    calls = 0,
    fail
  const original = api.defaults.adapter
  const unsubscribe = onBrowserContextChanged(() => {
    notifications++
  })
  const conflict = (config) =>
    new axios.AxiosError('changed', 'ERR_BAD_RESPONSE', config, null, {
      status: 409,
      config,
      data: {
        code: 409,
        message: 'context changed',
        data: { error_code: 'browser_context_changed' },
      },
    })
  try {
    api.defaults.adapter = async (config) => {
      calls++
      throw conflict(config)
    }
    await assert.rejects(api.put('/setting', {}), (error) => error.code === 409)
    assert.equal(calls, 1)
    assert.equal(notifications, 1)
    api.defaults.adapter = (config) =>
      new Promise((resolve, reject) => {
        fail = () => reject(conflict(config))
      })
    const old = api.put('/setting', {})
    const rejected = assert.rejects(old, (error) => error.code === 'session_changed')
    await Promise.resolve()
    invalidateSessionRequests()
    fail()
    await rejected
    assert.equal(notifications, 1)
  } finally {
    unsubscribe()
    api.defaults.adapter = original
    setBrowserContext()
  }
})

test('playback keepalive save and close retain the same context as normal JSON calls', async () => {
  const oldFetch = globalThis.fetch,
    oldDocument = globalThis.document
  const calls = []
  globalThis.document = { cookie: 'csrftoken=test-token' }
  globalThis.fetch = async (url, options) => {
    calls.push(options)
    return { ok: true, json: async () => ({}) }
  }
  try {
    setBrowserContext('login-a')
    await playbackApi.saveProgressOnLeave('session-a', {})
    await playbackApi.closeOnLeave({ session_id: 'session-a', version: 1 })
    assert.equal(calls.length, 2)
    assert.ok(
      calls.every(
        (options) => options.headers['X-NASSAV-Context'] === 'login-a' && options.keepalive
      )
    )
  } finally {
    globalThis.fetch = oldFetch
    globalThis.document = oldDocument
    setBrowserContext()
  }
})

test('disposed login state cannot publish a delayed bootstrap context', async () => {
  const { createPinia, setActivePinia } = await import('pinia')
  const { useSessionStore } = await import('../src/features/auth/stores/session.js')
  setActivePinia(createPinia())
  const original = api.defaults.adapter
  let finish
  api.defaults.adapter = (config) =>
    new Promise((resolve) => {
      finish = (data) => resolve({ config, status: 200, headers: {}, data: { code: 200, data } })
    })
  const session = useSessionStore()
  try {
    const pending = session.initialize()
    session.$dispose()
    setBrowserContext('new-owner')
    finish({
      authenticated: true,
      username: 'old',
      cache_identity: 'old-owner',
      capabilities: { ordinary_login: true },
    })
    await pending
    assert.deepEqual(browserContextHeaders(), { 'X-NASSAV-Context': 'new-owner' })
  } finally {
    api.defaults.adapter = original
    setBrowserContext()
  }
})
