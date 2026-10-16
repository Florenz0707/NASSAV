import { defineStore } from 'pinia'
import { onScopeDispose, ref } from 'vue'
import { viewingApi } from '../../../api/viewing.js'
import { onPersonalDataChanged } from '../../../shared/lib/personalDataEvents.js'

export const useViewingStore = defineStore('viewing', () => {
  const revision = ref(0)
  const cache = new Map(),
    pending = new Map()
  let generation = 0
  const epochs = new Map()
  function reset(kind = null) {
    revision.value++
    if (kind) {
      epochs.set(kind, (epochs.get(kind) || 0) + 1)
      for (const key of cache.keys()) if (key.startsWith(`${kind}:`)) cache.delete(key)
      for (const key of pending.keys()) if (key.startsWith(`${kind}:`)) pending.delete(key)
    } else {
      generation++
      epochs.clear()
      cache.clear()
      pending.clear()
    }
  }
  onScopeDispose(
    onPersonalDataChanged((event) => {
      if (!event.topics) reset()
      else
        for (const kind of ['history', 'watch-later'])
          if (event.topics.includes(kind) || event.topics.includes('library')) reset(kind)
    })
  )
  async function list(kind, page, size, force = false) {
    const key = `${kind}:${page}:${size}`,
      epoch = `${generation}:${epochs.get(kind) || 0}`
    const hit = cache.get(key)
    if (!force && hit && Date.now() - hit.time < 30000) return hit.value
    if (!force && pending.has(key)) return pending.get(key)
    const request = viewingApi
      .list(kind, page, size)
      .then((value) => {
        if (epoch !== `${generation}:${epochs.get(kind) || 0}` || pending.get(key) !== request)
          return null
        cache.delete(key)
        cache.set(key, { value, time: Date.now() })
        if (cache.size > 8) cache.delete(cache.keys().next().value)
        return value
      })
      .finally(() => {
        if (pending.get(key) === request) pending.delete(key)
      })
    pending.set(key, request)
    return request
  }
  return { revision, list, reset }
})
