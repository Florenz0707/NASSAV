import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, onUnauthorized } from '../../../api/index.js'
import { invalidateSessionRequests } from '../../../api/client.js'

export const useSessionStore = defineStore('session', () => {
  const status = ref('checking')
  const username = ref(null)
  const identity = ref('')
  const capabilities = ref({})
  let unsubscribe = null
  let requestVersion = 0

  function expire() {
    requestVersion++
    invalidateSessionRequests()
    status.value = 'anonymous'
    username.value = null
    identity.value = ''
    capabilities.value = {}
  }

  function accept(data) {
    if (!data?.authenticated) {
      expire()
      return false
    }
    // Old backend responses retain single-operator compatibility, with no new rights.
    const nextIdentity = data.cache_identity || `legacy:${data.username}`
    if (identity.value !== nextIdentity) invalidateSessionRequests()
    username.value = data.username
    identity.value = nextIdentity
    capabilities.value = data.capabilities || {}
    status.value = 'authenticated'
    return true
  }

  function attachUnauthorizedHandler() {
    if (!unsubscribe) unsubscribe = onUnauthorized(expire)
  }

  async function initialize() {
    attachUnauthorizedHandler()
    const version = ++requestVersion
    try {
      const response = await authApi.getSession()
      if (version === requestVersion) accept(response.data)
    } catch {
      if (version === requestVersion) expire()
    }
  }

  async function recheck() {
    attachUnauthorizedHandler()
    const version = ++requestVersion
    try {
      const response = await authApi.getSession()
      return version === requestVersion && accept(response.data)
    } catch (error) {
      if (version !== requestVersion) return false
      // Network outages do not prove a login has expired.
      if (error?.httpStatus === 401) expire()
      return status.value === 'authenticated'
    }
  }

  async function signIn(name, password) {
    attachUnauthorizedHandler()
    const version = ++requestVersion
    invalidateSessionRequests()
    const response = await authApi.login(name, password)
    if (version === requestVersion) accept(response.data)
  }

  async function signOut() {
    const version = ++requestVersion
    invalidateSessionRequests()
    await authApi.logout()
    if (version === requestVersion) expire()
  }

  return { status, username, identity, capabilities, initialize, recheck, signIn, signOut, expire }
})
