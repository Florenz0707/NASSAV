import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

const waiting = []
let account = {
  authenticated: true,
  username: 'same-name',
  cache_identity: 'login-a',
  capabilities: {},
}
const success = (config, data) => ({ config, status: 200, headers: {}, data: { code: 200, data } })
axios.defaults.adapter = (config) => {
  if (config.url === '/auth/login') return Promise.resolve(success(config, account))
  if (config.url === '/auth/logout')
    return Promise.resolve(success(config, { authenticated: false }))
  return new Promise((resolve, reject) => waiting.push({ config, resolve, reject }))
}
const { useSessionStore } = await import('../src/features/auth/stores/session.js')
const { default: api } = await import('../src/api/client.js')
const tick = () => new Promise((resolve) => setImmediate(resolve))

// Ordered subcases exercise the same live store and Axios interceptors.
test('old session, protected success and 401 cannot overwrite the current identity', async () => {
  setActivePinia(createPinia())
  const session = useSessionStore()
  const initialization = session.initialize()
  await tick()
  const oldInitialization = waiting.shift()
  await session.signIn('same-name', 'test')
  oldInitialization.resolve(success(oldInitialization.config, { authenticated: false }))
  await initialization
  assert.equal(session.identity, 'login-a')
  assert.equal(session.status, 'authenticated')

  const oldSuccess = api.get('/old-success')
  const oldUnauthorized = api.get('/old-unauthorized')
  // Attach rejection handlers before resolving to avoid unhandled promises.
  const successes = assert.rejects(oldSuccess, (error) => error.code === 'session_changed')
  const unauthorized = assert.rejects(oldUnauthorized, (error) => error.code === 'session_changed')
  await tick()
  const [one, two] = waiting.splice(0)
  account = { ...account, cache_identity: 'login-b', capabilities: { app_admin: true } }
  await session.signIn('same-name', 'test')
  one.resolve(success(one.config, { private: 'old-result' }))
  two.reject(
    new axios.AxiosError('expired', 'ERR_BAD_RESPONSE', two.config, null, {
      config: two.config,
      status: 401,
      data: { code: 401, message: 'expired' },
    })
  )
  await Promise.all([successes, unauthorized])
  assert.equal(session.status, 'authenticated')
  assert.equal(session.identity, 'login-b')
  assert.equal(session.capabilities.app_admin, true)

  const rechecking = session.recheck()
  await tick()
  const recheck = waiting.shift()
  recheck.resolve(
    success(recheck.config, {
      ...account,
      cache_identity: 'role-c',
      capabilities: { app_admin: false },
    })
  )
  assert.equal(await rechecking, true)
  assert.equal(session.identity, 'role-c')
  assert.equal(session.capabilities.app_admin, false)

  const offline = session.recheck()
  await tick()
  const network = waiting.shift()
  network.reject(new axios.AxiosError('offline', 'ERR_NETWORK', network.config))
  assert.equal(await offline, true)
  assert.equal(session.identity, 'role-c')
  await session.signOut()
  assert.equal(session.identity, '')
  assert.deepEqual(session.capabilities, {})
})
