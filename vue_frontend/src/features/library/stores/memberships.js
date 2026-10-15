import { defineStore } from 'pinia'
import { libraryApi } from '../../../api/library.js'
import { createMembershipLookup } from '../lib/membershipLookup.js'

export const useMembershipsStore = defineStore('memberships', () => {
  const visible = new Map()
  const lookup = createMembershipLookup(libraryApi.membershipStatuses, {
    protectedKeys: () => visible.values(),
  })
  let timer = null
  function stop() {
    if (timer) clearInterval(timer)
    timer = null
  }
  function retain(avid) {
    const token = Symbol()
    visible.set(token, avid.trim().toUpperCase())
    if (!timer)
      timer = setInterval(() => {
        if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
        lookup.schedule([...visible.values()], { force: true })
      }, 30000)
    return () => {
      visible.delete(token)
      lookup.prune()
      if (!visible.size) stop()
    }
  }
  function reset(identity = '') {
    stop()
    visible.clear()
    lookup.reset(identity)
  }
  return { ...lookup, reset, retain }
})
