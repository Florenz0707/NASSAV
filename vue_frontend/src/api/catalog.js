import api, { EXTERNAL_SEARCH_REQUEST_TIMEOUT, contextualImageUrl } from './client.js'

export const actorApi = {
  // 获取演员列表（聚合统计）
  getList: (params = {}) => api.get('/actors', { params }),
  // 获取演员详情（包括外部搜索）
  getDetail: (actorId, params = {}) =>
    api.get(`/actors/${actorId}/detail`, { params, timeout: EXTERNAL_SEARCH_REQUEST_TIMEOUT }),
  // 获取演员头像图片URL
  getAvatarUrl: (actorId) => {
    const base = api.defaults.baseURL.replace(/\/$/, '')
    return contextualImageUrl(`${base}/actors/${actorId}/avatar`)
  },
}

export const genreApi = {
  // 获取类别列表（聚合统计）
  getList: (params = {}) => api.get('/genres', { params }),
  // 获取类别详情（包括外部搜索）
  getDetail: (genreId, params = {}) =>
    api.get(`/genres/${genreId}/detail`, { params, timeout: EXTERNAL_SEARCH_REQUEST_TIMEOUT }),
}
