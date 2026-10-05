import { logger } from '../utils/logger.js'
import axios from 'axios'

const api = axios.create({
  baseURL: '/nassav/api',
  timeout: 30000,
  withCredentials: true,
  withXSRFToken: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    Pragma: 'no-cache',
    Expires: '0',
  },
})

const RECOMMENDATION_REQUEST_TIMEOUT = 120000
// Five source pages can each spend 60s in the browser plus direct/control work.
const EXTERNAL_SEARCH_REQUEST_TIMEOUT = 450000
const unauthorizedListeners = new Set()

export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function reportUnauthorized(error) {
  if (error.response?.status !== 401 || error.config?.url === '/auth/login') return
  for (const listener of unauthorizedListeners) listener()
}

// 响应拦截器：兼容后端统一的 envelope 格式 {code, message, data}
api.interceptors.response.use(
  (response) => {
    const envelope = response.data
    if (response.status >= 200 && response.status < 300) {
      // 如果是后端的 envelope 格式
      if (envelope && typeof envelope.code !== 'undefined') {
        const c = envelope.code
        // 后端可能使用 code=0 或 HTTP 风格 code (200-299) 表示成功
        const success = c === 0 || (typeof c === 'number' && c >= 200 && c < 300)
        if (success) {
          const data = envelope.data
          const pagination = envelope.pagination || (data && data.pagination) || null
          return { code: envelope.code, message: envelope.message, data, pagination }
        }
        return Promise.reject({
          httpStatus: response.status,
          code: envelope.code,
          message: envelope.message,
          data: envelope.data,
        })
      }
      // 非 envelope（例如二进制文件响应）直接返回原始 response
      return response
    }
    return Promise.reject({ httpStatus: response.status, data: envelope })
  },
  (error) => {
    reportUnauthorized(error)
    if (error.response) {
      const env = error.response.data
      if (env && typeof env.code !== 'undefined') {
        return Promise.reject({
          httpStatus: error.response.status,
          code: env.code,
          message: env.message,
          data: env.data,
        })
      }
      return Promise.reject({ httpStatus: error.response.status, data: env })
    }
    return Promise.reject({ code: 500, message: '网络错误', data: null })
  }
)

export const authApi = {
  getSession: () => api.get('/auth/session'),
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
}

// 下载源管理（包含设置 Cookie）
export const sourceApi = {
  getSearchCapabilities: () => api.get('/source/search-capabilities'),
  // 获取所有可用下载源列表
  getList: () => api.get('/source/list'),
  // 获取所有已设置的源 Cookie 列表
  getCookies: () => api.get('/source/cookie'),
  // 设置或自动获取 Cookie
  setCookie: (payload) => api.post('/source/cookie', payload),
  // 删除指定源的 Cookie
  deleteCookie: (source) => api.delete('/source/cookie', { params: { source } }),
}

export const externalSearchApi = {
  submit: (query, signal) => api.post('/search/jobs', query, { signal }),
  getJob: (taskId, token, signal, pagination = {}) =>
    api.get(`/search/jobs/${taskId}`, { params: { token, ...pagination }, signal }),
  cancelJob: (taskId, token) => api.post(`/search/jobs/${taskId}/cancel`, { token }),
}

// 用户设置管理
export const settingsApi = {
  // 获取用户设置
  get: () => api.get('/setting'),
  // 更新用户设置（支持部分更新）
  update: (payload) => api.put('/setting', payload),
}

// 推荐系统
export const recommendationApi = {
  // 获取推荐结果
  getList: (params = {}) =>
    api.get('/recommendations', {
      params,
      timeout: RECOMMENDATION_REQUEST_TIMEOUT,
    }),
  // 获取可用推荐器和策略
  getOptions: () => api.get('/recommendations/options'),
  // 获取推荐效果概览
  getMetrics: () => api.get('/recommendations/metrics'),
  // 提交推荐反馈
  submitFeedback: (payload) => api.post('/recommendations/feedback', payload),
  // 手动屏蔽推荐种子
  blockSeed: (payload) => api.post('/recommendations/seed-block', payload),
  // 取消屏蔽推荐种子
  unblockSeed: (payload) => api.delete('/recommendations/seed-block', { data: payload }),
  // 获取资源黑名单
  getAvidBlocklist: (params = {}) => api.get('/recommendations/avid-blocklist', { params }),
  // 手动加入资源黑名单
  blockAvid: (payload) => api.post('/recommendations/avid-blocklist', payload),
  // 取消资源黑名单
  unblockAvid: (payload) => api.delete('/recommendations/avid-blocklist', { data: payload }),
  // 清空推荐状态，默认由后端保留黑名单
  resetState: (payload = {}) => api.post('/recommendations/reset', payload),
  // 获取推荐封面代理地址
  getCoverUrl: (coverUrl, source = 'jable') => {
    const base = api.defaults.baseURL.replace(/\/$/, '')
    return `${base}/recommendations/cover?url=${encodeURIComponent(coverUrl || '')}&source=${encodeURIComponent(source.toLowerCase())}`
  },
}

// 演员管理
export const actorApi = {
  // 获取演员列表（聚合统计）
  getList: (params = {}) => api.get('/actors', { params }),
  // 获取演员详情（包括外部搜索）
  getDetail: (actorId, params = {}) =>
    api.get(`/actors/${actorId}/detail`, { params, timeout: EXTERNAL_SEARCH_REQUEST_TIMEOUT }),
  // 获取演员头像图片URL
  getAvatarUrl: (actorId) => {
    const base = api.defaults.baseURL.replace(/\/$/, '')
    return `${base}/actors/${actorId}/avatar`
  },
}

// 类别管理
export const genreApi = {
  // 获取类别列表（聚合统计）
  getList: (params = {}) => api.get('/genres', { params }),
  // 获取类别详情（包括外部搜索）
  getDetail: (genreId, params = {}) =>
    api.get(`/genres/${genreId}/detail`, { params, timeout: EXTERNAL_SEARCH_REQUEST_TIMEOUT }),
}

// 资源管理
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

  // 更新资源状态（观看状态和收藏状态）
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

// 下载管理
export const downloadApi = {
  // 获取视频文件路径
  getFilePath: (avid) => api.get('/downloads/abspath', { params: { avid } }),

  // 提交下载任务
  submitDownload: (avid) => api.post(`/downloads/${encodeURIComponent(avid)}`),

  // 删除下载的视频
  deleteFile: (avid) => api.delete(`/downloads/${encodeURIComponent(avid)}`),
  // 批量提交下载任务（动态超时）
  batchSubmit: (avids) => {
    // 基础超时 10 秒，每个任务增加 2 秒
    const timeout = 10000 + avids.length * 2000
    logger.debug(`[API] 批量下载 ${avids.length} 个任务，超时设置: ${timeout}ms`)
    return api.post('/downloads/batch_submit', { avids }, { timeout })
  },
}

// 任务管理
export const taskApi = {
  // 获取任务队列状态
  getQueueStatus: () => api.get('/tasks/queue/status'),
}
