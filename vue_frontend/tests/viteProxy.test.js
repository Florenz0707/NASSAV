import assert from 'node:assert/strict'
import { createServer as createHttpServer, request } from 'node:http'
import { connect } from 'node:net'
import { once } from 'node:events'
import { test } from 'node:test'
import { createServer as createViteServer } from 'vite'

function httpGet(port, headers) {
  return new Promise((resolve, reject) => {
    const req = request(
      { hostname: '127.0.0.1', port, path: '/nassav/api/probe', headers },
      (res) => {
        const chunks = []
        res.on('data', (chunk) => chunks.push(chunk))
        res.on('end', () =>
          resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() })
        )
      }
    )
    req.on('error', reject)
    req.end()
  })
}

function websocketUpgrade(port, headers) {
  return new Promise((resolve, reject) => {
    const socket = connect(port, '127.0.0.1')
    socket.setTimeout(5000)
    socket.on('error', reject)
    socket.on('timeout', () => socket.destroy(new Error('WebSocket proxy timed out')))
    socket.on('data', (data) => {
      resolve(data.toString())
      socket.destroy()
    })
    socket.on('connect', () => {
      socket.write(
        'GET /nassav/ws/tasks/ HTTP/1.1\r\n' +
          `Host: ${headers.host}\r\n` +
          `Origin: ${headers.origin}\r\n` +
          'Cookie: sessionid=test-session\r\n' +
          'Connection: Upgrade\r\n' +
          'Upgrade: websocket\r\n' +
          'Sec-WebSocket-Version: 13\r\n' +
          'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n'
      )
    })
  })
}

test('Vite proxies HTTP and WebSocket under the page host with session cookie and Origin', async () => {
  let httpHeaders
  let wsHeaders
  const backend = createHttpServer((req, res) => {
    httpHeaders = req.headers
    res.writeHead(200, { 'Content-Type': 'text/plain' })
    res.end('backend-ok')
  })
  backend.on('upgrade', (req, socket) => {
    wsHeaders = req.headers
    socket.write(
      'HTTP/1.1 101 Switching Protocols\r\n' +
        'Upgrade: websocket\r\n' +
        'Connection: Upgrade\r\n' +
        'Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n'
    )
    socket.end()
  })
  backend.listen(0, '127.0.0.1')
  await once(backend, 'listening')
  const originalBackend = process.env.NASSAV_VITE_BACKEND_URL
  const originalHost = process.env.NASSAV_VITE_HOST
  process.env.NASSAV_VITE_BACKEND_URL = `http://127.0.0.1:${backend.address().port}`
  process.env.NASSAV_VITE_HOST = '127.0.0.1'
  let vite
  try {
    const { default: config } = await import(`../vite.config.js?probe=${Date.now()}`)
    assert.equal(config.server.host, '127.0.0.1')
    assert.equal(config.server.proxy['/nassav/ws'].ws, true)
    vite = await createViteServer({
      ...config,
      configFile: false,
      server: { ...config.server, port: 0 },
    })
    await vite.listen()
    const port = vite.httpServer.address().port
    const host = `192.0.2.8:${port}`
    const origin = `http://${host}`
    const headers = { Host: host, Origin: origin, Cookie: 'sessionid=test-session' }
    const http = await httpGet(port, headers)
    assert.equal(http.status, 200)
    assert.equal(http.body, 'backend-ok')
    assert.equal(httpHeaders.host, host)
    assert.equal(httpHeaders.cookie, 'sessionid=test-session')
    const ws = await websocketUpgrade(port, { host, origin })
    assert.match(ws, /^HTTP\/1\.1 101/)
    assert.equal(wsHeaders.host, host)
    assert.equal(wsHeaders.origin, origin)
    assert.equal(wsHeaders.cookie, 'sessionid=test-session')
  } finally {
    if (vite) await vite.close()
    backend.closeAllConnections()
    await new Promise((resolve) => backend.close(resolve))
    if (originalBackend === undefined) delete process.env.NASSAV_VITE_BACKEND_URL
    else process.env.NASSAV_VITE_BACKEND_URL = originalBackend
    if (originalHost === undefined) delete process.env.NASSAV_VITE_HOST
    else process.env.NASSAV_VITE_HOST = originalHost
  }
})

test('cross-device Vite listener and HTTPS backend select the expected proxy transports', async () => {
  const originalBackend = process.env.NASSAV_VITE_BACKEND_URL
  const originalHost = process.env.NASSAV_VITE_HOST
  process.env.NASSAV_VITE_BACKEND_URL = 'https://backend.example:9790'
  process.env.NASSAV_VITE_HOST = '0.0.0.0'
  try {
    const { default: config } = await import(`../vite.config.js?remote=${Date.now()}`)
    assert.equal(config.server.host, '0.0.0.0')
    assert.equal(config.server.proxy['/nassav/api'].target, 'https://backend.example:9790')
    assert.equal(config.server.proxy['/nassav/ws'].target, 'wss://backend.example:9790')
  } finally {
    if (originalBackend === undefined) delete process.env.NASSAV_VITE_BACKEND_URL
    else process.env.NASSAV_VITE_BACKEND_URL = originalBackend
    if (originalHost === undefined) delete process.env.NASSAV_VITE_HOST
    else process.env.NASSAV_VITE_HOST = originalHost
  }
})
