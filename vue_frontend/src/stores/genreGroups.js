import { genreApi } from '../api/index.js'
import { createRequestGuard } from '../utils/requestGuard.js'
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useGenreGroupsStore = defineStore('genreGroups', () => {
  const groups = ref([])
  const pagination = ref({ total: 0, page: 1, page_size: 15, pages: 1 })
  const loading = ref(false)
  const error = ref(null)

  const guard = createRequestGuard()

  // direct call to /genres to get groups
  async function load({
    page = 1,
    page_size = 15,
    order_by = 'count',
    order = 'desc',
    search,
  } = {}) {
    const request = guard.begin()
    loading.value = true
    error.value = null
    try {
      const params = { page, page_size, order_by, order }
      if (String(search || '').trim()) params.search = String(search).trim()
      const response = await genreApi.getList(params)
      if (!guard.current(request)) return
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

  return { groups, pagination, loading, error, load, cancel }
})
