import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, onUnauthorized } from '../api/index.js'

export const useSessionStore = defineStore('session', () => {
  const status = ref('checking')
  const username = ref(null)
  let unsubscribe = null

  function expire() {
    status.value = 'anonymous'
    username.value = null
  }

  function attachUnauthorizedHandler() {
    if (!unsubscribe) unsubscribe = onUnauthorized(expire)
  }

  async function initialize() {
    attachUnauthorizedHandler()
    try {
      const response = await authApi.getSession()
      if (response.data.authenticated) {
        status.value = 'authenticated'
        username.value = response.data.username
      } else {
        expire()
      }
    } catch {
      expire()
    }
  }

  async function signIn(name, password) {
    const response = await authApi.login(name, password)
    username.value = response.data.username
    status.value = 'authenticated'
  }

  async function signOut() {
    await authApi.logout()
    expire()
  }

  return { status, username, initialize, signIn, signOut, expire }
})
