import { reactive, watch } from 'vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'

export function createAdminRead(fetchList, currentOwner) {
  const owner = currentOwner(),
    guard = createRequestGuard()
  const state = reactive({ rows: [], pagination: null, loading: false, error: '' })
  let active = true
  const owns = () => active && Boolean(owner) && currentOwner() === owner
  const stopOwner = watch(
    currentOwner,
    () => {
      if (!owns()) dispose()
    },
    { flush: 'sync' }
  )
  async function load(params) {
    if (!owns()) return
    const request = guard.begin()
    state.loading = true
    state.error = ''
    try {
      const response = await fetchList(params)
      if (!owns() || !guard.current(request)) return
      if (!Array.isArray(response.data)) throw new Error('管理列表格式无效')
      state.rows = response.data
      state.pagination = response.pagination || null
    } catch (error) {
      if (owns() && guard.current(request)) state.error = error.message || '无法读取管理信息'
    } finally {
      if (owns() && guard.current(request)) state.loading = false
    }
  }
  function dispose() {
    active = false
    guard.invalidate()
    stopOwner()
    state.rows = []
    state.pagination = null
    state.loading = false
    state.error = ''
  }
  return Object.assign(state, { load, dispose })
}
