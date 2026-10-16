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
import { buildTaskDetails } from '../src/features/tasks/lib/taskDetails.js'
import { buildOperationDetails } from '../src/features/tasks/lib/operationDetails.js'

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

test('server-provided generic covers get one current context without altering other image routes', () => {
  setBrowserContext('new-login')
  try {
    const raw = '/nassav/api/resource/cover?avid=YUJ-036&size=small&v=version-1'
    const result = new URL(resourceApi.resolveCoverUrl(raw), 'https://app.invalid')
    assert.equal(result.searchParams.get('_context'), 'new-login')
    assert.equal(result.searchParams.get('size'), 'small')
    assert.equal(result.searchParams.get('v'), 'version-1')
    const stale = resourceApi.resolveCoverUrl(`${raw}&_context=old&_context=older`)
    assert.deepEqual(new URL(stale, 'https://app.invalid').searchParams.getAll('_context'), [
      'new-login',
    ])
    assert.equal(resourceApi.resolveCoverUrl(stale), stale)
    for (const url of [
      '/nassav/api/library/entries/entry/images/handle',
      '/nassav/api/recommendations/cover?handle=owned',
      'https://cdn.invalid/cover.jpg',
      'blob:https://app.invalid/example',
    ])
      assert.equal(resourceApi.resolveCoverUrl(url), url)
  } finally {
    setBrowserContext()
  }
})

test('legacy and shared task projections use the supplied cover context resolver', () => {
  setBrowserContext('task-login')
  try {
    const resource = {
      avid: 'YUJ-036',
      membership_state: 'active',
      thumbnail_url: '/nassav/api/resource/cover?avid=YUJ-036&size=small',
    }
    const legacy = buildTaskDetails({
      active: [{ avid: resource.avid, task_id: 'legacy', state: 'STARTED' }],
      resources: [resource],
      coverUrlFor: resourceApi.getCoverUrl,
      resolveCoverUrl: resourceApi.resolveCoverUrl,
    })
    const shared = buildOperationDetails(
      [{ operation_id: 'operation', avid: resource.avid, kind: 'scrape', state: 'running' }],
      [resource],
      undefined,
      resourceApi.resolveCoverUrl
    )
    for (const task of [...legacy, ...shared]) {
      const url = new URL(task.coverUrl, 'https://app.invalid')
      assert.equal(url.searchParams.get('_context'), 'task-login')
      assert.equal(url.searchParams.get('size'), 'small')
    }
  } finally {
    setBrowserContext()
  }
})
