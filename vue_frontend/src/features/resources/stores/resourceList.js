import { ref } from 'vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'

export function createResourceList(resourceApi) {
  const resources = ref([]),
    loading = ref(false),
    error = ref(null)
  const resourceQueryGuard = createRequestGuard()
  let lastResourceQuery = null
  const pagination = ref({ total: 0, page: 1, page_size: 20, pages: 1 })

  async function fetchResources({
    sort_by = 'metadata_create_time',
    order = 'desc',
    page = 1,
    page_size = 20,
    search = '',
    status = 'all',
    actor = undefined,
    genre = undefined,
    watched = undefined,
    is_favorite = undefined,
  } = {}) {
    const request = resourceQueryGuard.begin()
    loading.value = true
    error.value = null
    try {
      const params = { sort_by, order, page, page_size }
      lastResourceQuery = {
        sort_by,
        order,
        page,
        page_size,
        search,
        status,
        actor,
        genre,
        watched,
        is_favorite,
      }
      if (search) params.search = search
      if (status && status !== 'all') params.status = status
      if (typeof actor !== 'undefined' && actor !== null && actor !== '') params.actor = actor
      if (typeof genre !== 'undefined' && genre !== null && genre !== '') params.genre = genre
      if (typeof watched !== 'undefined') params.watched = watched
      if (typeof is_favorite !== 'undefined') params.is_favorite = is_favorite
      const response = await resourceApi.getList(params)
      if (!resourceQueryGuard.current(request)) return

      // 后端可能返回多种格式：
      // 1) envelope with data as an array -> { data: [ ... ], pagination?: {...} }
      // 2) envelope with data.results and data.pagination -> { data: { results: [...], pagination: {...} } }
      // 3) legacy or other -> response.data may already be the array
      let results = []
      let paginationObj = null

      if (response) {
        // case: response.data is array
        if (Array.isArray(response.data)) {
          results = response.data
          paginationObj = response.pagination || null
        }
        // case: response.data.metadata exists (new backend shape)
        else if (response.data && Array.isArray(response.data.metadata)) {
          results = response.data.metadata
          // map backend pagination fields to our pagination shape
          paginationObj = {
            total:
              response.data.total_num ||
              (response.data.pagination && response.data.pagination.total) ||
              (response.pagination && response.pagination.total) ||
              0,
            pages:
              response.data.total_pages ||
              (response.data.pagination && response.data.pagination.pages) ||
              (response.pagination && response.pagination.pages) ||
              1,
            page: page,
            page_size: page_size,
          }
        }
        // case: response.data.results exists
        else if (response.data && Array.isArray(response.data.results)) {
          results = response.data.results
          paginationObj = response.data.pagination || response.pagination || null
        }
        // case: response itself is an array (unlikely)
        else if (Array.isArray(response)) {
          results = response
        } else {
          results = response.data || []
          paginationObj = response.pagination || (response.data && response.data.pagination) || null
        }
      }

      resources.value = results || []
      if (paginationObj) {
        pagination.value = Object.assign({}, pagination.value, paginationObj)
      } else {
        // ensure pagination.page at least matches request
        pagination.value.page = page
        pagination.value.page_size = page_size
      }
    } catch (err) {
      if (!resourceQueryGuard.current(request)) return
      error.value = err.message || '获取资源列表失败'
      throw err
    } finally {
      if (resourceQueryGuard.current(request)) loading.value = false
    }
  }

  function cancelResourceQuery() {
    resourceQueryGuard.invalidate()
    loading.value = false
    lastResourceQuery = null
  }

  function refresh() {
    return lastResourceQuery ? fetchResources(lastResourceQuery) : Promise.resolve()
  }
  return { resources, loading, error, pagination, fetchResources, cancelResourceQuery, refresh }
}
