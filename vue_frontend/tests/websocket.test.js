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

const { taskWebSocketUrl, useWebSocketStore } = await import('../src/stores/websocket.js')
const { useSessionStore } = await import('../src/stores/session.js')
const { useResourceStore } = await import('../src/stores/resource.js')

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  static instances = []
  constructor(url) {
    this.url = url
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
