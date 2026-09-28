import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

let authenticated = false
let rejectNextProtectedRequest = false
const requests = []

function response(config, status, data) {
  return {
    config,
    status,
    statusText: status === 200 ? 'OK' : 'Unauthorized',
    headers: {},
    data: { code: status, message: status === 200 ? 'success' : '请先登录', data },
  }
}

axios.defaults.adapter = async (config) => {
  requests.push(config)
  if (config.url === '/auth/session') {
    return response(config, 200, {
      authenticated,
      username: authenticated ? 'nassav' : null,
    })
  }
  if (config.url === '/auth/login') {
    authenticated = true
    return response(config, 200, { authenticated: true, username: 'nassav' })
  }
  if (config.url === '/auth/logout') {
    authenticated = false
    return response(config, 200, { authenticated: false })
  }
  if (config.url === '/setting' && rejectNextProtectedRequest) {
    rejectNextProtectedRequest = false
    throw new axios.AxiosError(
      'Unauthorized',
      'ERR_BAD_RESPONSE',
      config,
      null,
      response(config, 401, null)
    )
  }
  throw new Error(`Unexpected request ${config.url}`)
}

const { useSessionStore } = await import('../src/stores/session.js')
const { settingsApi } = await import('../src/api/index.js')

test('login, expiry and logout update the session gate', async () => {
  setActivePinia(createPinia())
  const session = useSessionStore()
  await session.initialize()
  assert.equal(session.status, 'anonymous')
  await session.signIn('nassav', 'test-only-password')
  assert.equal(session.status, 'authenticated')
  assert.equal(session.username, 'nassav')
  rejectNextProtectedRequest = true
  await assert.rejects(settingsApi.get())
  assert.equal(session.status, 'anonymous')
  await session.signIn('nassav', 'test-only-password')
  await session.signOut()
  assert.equal(session.status, 'anonymous')
  assert.equal(session.username, null)
  assert.ok(requests.every((request) => request.withCredentials === true))
  assert.ok(requests.every((request) => request.withXSRFToken === true))
})
