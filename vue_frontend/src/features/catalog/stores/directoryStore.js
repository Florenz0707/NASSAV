import { createQueryCache } from '../../../shared/lib/queryCache.js'
import { onPersonalDataChanged } from '../../../shared/lib/personalDataEvents.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'
import { defineStore } from 'pinia'
import { ref, onScopeDispose } from 'vue'

export function createDirectoryStore(name, api) {
  return defineStore(name, () => {
    const groups = ref([])
    const pagination = ref({ total: 0, page: 1, page_size: 15, pages: 1 })
    const loading = ref(false)
    const error = ref(null)

    const guard = createRequestGuard()
    const cache = createQueryCache()
    function invalidate() {
      cache.clear()
      cancel()
    }
    onScopeDispose(onPersonalDataChanged(invalidate))

    // direct call to /actors to get groups
    async function load({
      page = 1,
      page_size = 15,
      order_by = 'count',
      order = 'desc',
      search,
      force = false,
    } = {}) {
      const request = guard.begin()
      loading.value = true
      error.value = null
      try {
        const params = { page, page_size, order_by, order }
        if (String(search || '').trim()) params.search = String(search).trim()
        const key = JSON.stringify(params)
        const hit = !force && cache.peek(key)
        if (hit) {
          groups.value = hit.value.data || []
          pagination.value = hit.value.pagination || pagination.value
          loading.value = !hit.fresh
        }
        const response = await cache.read(key, () => api.getList(params), { force })
        if (!guard.current(request) || !response) return
        groups.value = response.data || []
        pagination.value = response.pagination || pagination.value
      } catch (err) {
        if (!guard.current(request)) return
        error.value = err.message || String(err)
      } finally {
        if (guard.current(request)) loading.value = false
      }
    }

    function cancel() {
      guard.invalidate()
      loading.value = false
    }

    function reset() {
      cache.clear()
      cancel()
      groups.value = []
      error.value = null
      pagination.value = { total: 0, page: 1, page_size: 15, pages: 1 }
    }
    return { groups, pagination, loading, error, load, cancel, reset, invalidate }
  })
}
