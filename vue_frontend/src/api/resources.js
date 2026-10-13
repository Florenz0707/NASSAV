import api from './client.js'
import { logger } from '../shared/lib/logger.js'

export const resourceApi = {
  // 获取所有已保存资源列表（推荐使用新的 /resources 统一入口）
  getList: (params = {}) => api.get('/resources', { params }),

  // 获取资源预览信息（首屏快速渲染）
  getPreview: (avid) => api.get(`/resource/${encodeURIComponent(avid)}/preview`),

  // 获取资源元数据
  // bypassCache: 是否绕过浏览器缓存（添加时间戳参数）
  getMetadata: (avid, bypassCache = false) => {
    const params = { avid }
    if (bypassCache) {
      params._t = Date.now()
    }
    return api.get('/resource/metadata', { params })
  },

  // 获取封面图片URL（基于 axios 实例的 baseURL）
  // size: 'small'|'medium'|'large' or undefined for original
  getCoverUrl: (avid, size) => {
    const base = api.defaults.baseURL.replace(/\/$/, '')
    let url = `${base}/resource/cover?avid=${encodeURIComponent(avid)}`
    if (size) url += `&size=${encodeURIComponent(size)}`
    return url
  },
  // 简单的 LRU 缓存用于封面 object URLs，避免重复下载并支持自动回收
  // keyed by avid -> objectUrl
  _coverCache: new Map(),
  _maxCoverCache: 100,
  // 以 blob 形式获取封面（服务器返回 FileResponse / 二进制）
  fetchCoverBlob: async (avid) => {
    const resp = await api.get('/resource/cover', { params: { avid }, responseType: 'blob' })
    if (resp && typeof resp.code !== 'undefined') {
      if (resp.code === 0) return resp.data
      throw resp
    }
    return resp.data
  },
  // 获取封面对应的 object URL（使用缓存，按需请求）
  getCoverObjectUrl: async (avid) => {
    if (!avid) return null
    // 已缓存直接返回（并刷新为最近使用）
    if (resourceApi._coverCache.has(avid)) {
      const url = resourceApi._coverCache.get(avid)
      // move to end to mark as recently used
      resourceApi._coverCache.delete(avid)
      resourceApi._coverCache.set(avid, url)
      return url
    }
    try {
      const blob = await resourceApi.fetchCoverBlob(avid)
      if (!blob) throw new Error('no blob')
      const obj = URL.createObjectURL(blob)
      resourceApi._coverCache.set(avid, obj)
      // enforce size limit
      if (resourceApi._coverCache.size > resourceApi._maxCoverCache) {
        const firstKey = resourceApi._coverCache.keys().next().value
        const firstUrl = resourceApi._coverCache.get(firstKey)
        try {
          URL.revokeObjectURL(firstUrl)
        } catch {
          // Ignore revoke errors
        }
        resourceApi._coverCache.delete(firstKey)
      }
      return obj
    } catch (_e) {
      // fallback to URL
      return `${api.defaults.baseURL.replace(/\/$/, '')}/resource/cover?avid=${encodeURIComponent(avid)}`
    }
  },
  // 明确撤销并删除缓存项
  revokeCoverObjectUrl: (avid) => {
    if (resourceApi._coverCache.has(avid)) {
      const url = resourceApi._coverCache.get(avid)
      try {
        URL.revokeObjectURL(url)
      } catch {
        // Ignore revoke errors
      }
      resourceApi._coverCache.delete(avid)
    }
  },

  // 添加/刷新资源时只提交任务；终态由状态接口确认
  addNew: (avid, source = 'any') => api.post('/resource/jobs', { action: 'add', avid, source }),
  refresh: (avid, params = null) =>
    api.post('/resource/jobs', { action: 'refresh', avid, ...(params || {}) }),
  submitScrapeBatch: (actions) => api.post('/resource/jobs/batch', { actions }),
  getScrapeJob: (taskId, token) =>
    api.get(`/resource/jobs/${encodeURIComponent(taskId)}`, {
      headers: { 'X-Resource-Job-Token': token },
    }),

  // 删除资源
  delete: (avid) => api.delete(`/resource/${encodeURIComponent(avid)}`),

  // 更新个人资源状态（观看、收藏、备注及可选 expected_version）
  updateStatus: (avid, payload) =>
    api.patch(`/resource/${encodeURIComponent(avid)}/status`, payload),

  // 批量操作：body 应包含 { actions: [ {action, avid, ...}, ... ] }
  batch: (payload) => {
    const actions = payload.actions || []
    let baseTimeout = 15000 // 基础 15 秒
    let timeoutPerItem = 3000 // 每个资源 3 秒

    // 如果 actions 为空但有 avids (旧格式兼容性处理，虽然建议统一使用 actions)
    const count = actions.length || (payload.avids ? payload.avids.length : 0)
    const actionType = actions.length > 0 ? actions[0].action : payload.action || 'unknown'

    // 根据操作类型调整
    if (actionType === 'add') {
      timeoutPerItem = 5000 // 添加操作需要抓取元数据，更耗时
    } else if (actionType === 'refresh') {
      timeoutPerItem = 4000
    }

    const timeout = baseTimeout + count * timeoutPerItem
    logger.debug(`[API] 批量${actionType} ${count} 个任务，超时: ${timeout}ms`)

    return api.post('/resources/batch', payload, { timeout })
  },
}
