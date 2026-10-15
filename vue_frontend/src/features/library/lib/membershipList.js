import { ref } from 'vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'

export function createMembershipList(fetchList) {
  const rows = ref([]),
    loading = ref(false),
    error = ref('')
  const pagination = ref({ total: 0, page: 1, pages: 1, page_size: 20 })
  const guard = createRequestGuard()
  async function load(params) {
    const request = guard.begin()
    loading.value = true
    error.value = ''
    try {
      const response = await fetchList({ ...params })
      if (!guard.current(request)) return
      if (!Array.isArray(response.data) || !Number.isInteger(response.pagination?.total))
        throw new Error('持有列表格式无效')
      rows.value = response.data
      pagination.value = response.pagination
    } catch (reason) {
      if (guard.current(request)) error.value = reason.message || '无法读取本人持有关系'
    } finally {
      if (guard.current(request)) loading.value = false
    }
  }
  function dispose() {
    guard.invalidate()
    rows.value = []
    loading.value = false
  }
  return { rows, loading, error, pagination, load, dispose }
}
