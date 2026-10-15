import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

let authenticated = true
let networkDown = false
axios.defaults.adapter = async (config) => {
  if (config.url !== '/auth/session') throw new Error(`Unexpected request: ${config.url}`)
  if (networkDown) throw new Error('network unavailable')
  return {
    config,
    status: 200,
    statusText: 'OK',
    headers: {},
    data: {
      code: 200,
      message: 'success',
      data: {
        authenticated,
        username: authenticated ? 'nassav' : null,
      },
    },
  }
}

const { taskWebSocketUrl, useWebSocketStore } = await import('../src/app/stores/websocket.js')
const { useSessionStore } = await import('../src/features/auth/stores/session.js')
const { useResourceStore } = await import('../src/features/resources/stores/resource.js')

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  static instances = []
  constructor(url, protocols) {
    this.url = url
    this.protocols = protocols
    this.readyState = FakeWebSocket.CONNECTING
    FakeWebSocket.instances.push(this)
  }
  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }
  async closeWith(code) {
    this.readyState = FakeWebSocket.CLOSED
    await this.onclose?.({ code, reason: '' })
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED
  }
}

function setup() {
  const original = {
    window: globalThis.window,
    WebSocket: globalThis.WebSocket,
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
  }
  const timers = new Map()
  let nextTimer = 1
  globalThis.window = { location: { protocol: 'http:', host: '192.0.2.8:9780' } }
  globalThis.WebSocket = FakeWebSocket
  globalThis.setTimeout = (callback, delay) => {
    const id = nextTimer++
    timers.set(id, { callback, delay })
    return id
  }
  globalThis.clearTimeout = (id) => timers.delete(id)
  FakeWebSocket.instances.length = 0
  authenticated = true
  networkDown = false
  setActivePinia(createPinia())
  const session = useSessionStore()
  session.status = 'authenticated'
  const resource = useResourceStore()
  let snapshots = 0
  resource.refreshPendingScrapeJobs = async () => {
    snapshots += 1
  }
  const socketStore = useWebSocketStore()
  return {
    session,
    socketStore,
    timers,
    snapshots: () => snapshots,
    async fire(delay) {
      const item = [...timers].find(([, timer]) => timer.delay === delay)
      assert.ok(item, `Missing ${delay}ms timer`)
      timers.delete(item[0])
      await item[1].callback()
    },
    cleanup() {
      socketStore.disconnect()
      globalThis.window = original.window
      globalThis.WebSocket = original.WebSocket
      globalThis.setTimeout = original.setTimeout
      globalThis.clearTimeout = original.clearTimeout
    },
  }
}

test('WebSocket URL follows the page host and selects ws/wss', () => {
  assert.equal(
    taskWebSocketUrl({ protocol: 'http:', host: '192.0.2.8:9780' }),
    'ws://192.0.2.8:9780/nassav/ws/tasks/'
  )
  assert.equal(
    taskWebSocketUrl({ protocol: 'https:', host: 'nas.example:443' }),
    'wss://nas.example:443/nassav/ws/tasks/'
  )
})

test('failed handshake checks session, reconnects, and refreshes pending snapshots', async () => {
  const state = setup()
  try {
    state.socketStore.connect()
    state.socketStore.connect()
    assert.equal(FakeWebSocket.instances.length, 1)
    assert.equal(FakeWebSocket.instances[0].url, 'ws://192.0.2.8:9780/nassav/ws/tasks/')
    await FakeWebSocket.instances[0].closeWith(1006)
    assert.equal(state.session.status, 'authenticated')
    assert.equal(state.socketStore.connectionFailed, true)
    await state.fire(3000)
    assert.equal(FakeWebSocket.instances.length, 2)
    FakeWebSocket.instances[1].open()
    assert.equal(state.socketStore.connected, true)
    assert.equal(state.socketStore.connectionFailed, false)
    assert.equal(state.snapshots(), 1)
  } finally {
    state.cleanup()
  }
})

test('failed handshake with expired session stops reconnecting', async () => {
  const state = setup()
  try {
    authenticated = false
    state.socketStore.connect()
    await FakeWebSocket.instances[0].closeWith(1006)
    assert.equal(state.session.status, 'anonymous')
    assert.equal(state.timers.size, 0)
  } finally {
    state.cleanup()
  }
})

test('network outage keeps session and schedules reconnect', async () => {
  const state = setup()
  try {
    networkDown = true
    state.socketStore.connect()
    await FakeWebSocket.instances[0].closeWith(1006)
    assert.equal(state.session.status, 'authenticated')
    assert.equal(state.socketStore.connectionFailed, true)
    await state.fire(3000)
    assert.equal(FakeWebSocket.instances.length, 2)
  } finally {
    state.cleanup()
  }
})

test('connection timeout exposes failure for HTTP polling and retries', async () => {
  const state = setup()
  try {
    state.socketStore.connect()
    await state.fire(5000)
    assert.equal(state.socketStore.connectionFailed, true)
    assert.equal(state.socketStore.connected, false)
    await state.fire(3000)
    assert.equal(FakeWebSocket.instances.length, 2)
  } finally {
    state.cleanup()
  }
})

test('accepted socket closed with 4401 expires the session without retry', async () => {
  const state = setup()
  try {
    state.socketStore.connect()
    FakeWebSocket.instances[0].open()
    await FakeWebSocket.instances[0].closeWith(4401)
    assert.equal(state.session.status, 'anonymous')
    assert.equal(state.timers.size, 0)
  } finally {
    state.cleanup()
  }
})

test('origin rejection closes without retry', async () => {
  const state = setup()
  try {
    state.socketStore.connect()
    await FakeWebSocket.instances[0].closeWith(4403)
    assert.equal(state.session.status, 'authenticated')
    assert.equal(state.timers.size, 0)
  } finally {
    state.cleanup()
  }
})

test('search WebSocket events reach active search subscribers', async () => {
  const { subscribeSearchJobUpdates } =
    await import('../src/features/external-search/composables/searchJobEvents.js')
  const events = []
  const unsubscribe = subscribeSearchJobUpdates((event) => events.push(event))
  const state = setup()
  try {
    state.socketStore.connect()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    const data = { task_id: 'search-id', state: 'running', version: 3, updated_at: 10 }
    socket.onmessage({ data: JSON.stringify({ type: 'external_search_update', data }) })
    assert.deepEqual(events, [data])
    unsubscribe()
    socket.onmessage({ data: JSON.stringify({ type: 'external_search_update', data }) })
    assert.equal(events.length, 1)
  } finally {
    unsubscribe()
    state.cleanup()
  }
})

test('shared mode routes only own operation hints and never starts legacy queue tracking', async () => {
  const context = setup()
  const { useUserOperationsStore } = await import('../src/features/tasks/stores/userOperations.js')
  const { useDownloadQueueStore } =
    await import('../src/features/resources/stores/downloadQueue.js')
  const { useTaskJobsStore } = await import('../src/features/tasks/stores/taskJobs.js')
  context.session.capabilities = { shared_library: true }
  const operations = useUserOperationsStore(),
    hints = []
  let reads = 0
  operations.poll = () => {
    reads++
  }
  operations.load = () => {
    reads++
  }
  operations.hint = (event) => hints.push(event)
  useDownloadQueueStore().startTracking = () => {
    throw new Error('legacy queue must stay closed')
  }
  useTaskJobsStore().load = () => {
    throw new Error('legacy jobs must stay closed')
  }
  try {
    context.socketStore.connect()
    const socket = FakeWebSocket.instances.at(-1)
    socket.open()
    assert.equal(reads, 2)
    assert.equal(context.snapshots(), 0)
    socket.onmessage({
      data: JSON.stringify({ type: 'task_job_update', data: { job_id: 'shared', version: 4 } }),
    })
    socket.onmessage({
      data: JSON.stringify({
        type: 'user_operation_update',
        data: { operation_id: 'mine', version: 5 },
      }),
    })
    assert.deepEqual(hints, [{ operation_id: 'mine', version: 5 }])
  } finally {
    context.cleanup()
  }
})

test('managed sockets bind the expected context and recheck a changed cookie login before expiring', async () => {
  const state = setup()
  try {
    state.session.identity = 'login-a'
    state.session.capabilities = { ordinary_login: true, shared_library: true }
    state.socketStore.connect()
    assert.deepEqual(FakeWebSocket.instances[0].protocols, [
      'nassav.tasks.v1',
      'nassav.context.login-a',
    ])
    state.session.recheck = async () => {
      state.session.identity = 'login-b'
      return true
    }
    await FakeWebSocket.instances[0].closeWith(4401)
    assert.equal(state.session.status, 'authenticated')
    assert.equal(state.session.identity, 'login-b')
    await state.fire(3000)
    assert.deepEqual(FakeWebSocket.instances[1].protocols, [
      'nassav.tasks.v1',
      'nassav.context.login-b',
    ])
  } finally {
    state.cleanup()
  }
})
