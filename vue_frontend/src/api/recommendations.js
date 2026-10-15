import api, { RECOMMENDATION_REQUEST_TIMEOUT } from './client.js'

export const recommendationApi = {
  startJob: (params = {}) => api.post('/recommendations/jobs', params),
  getJob: (id, options = {}) => api.get(`/recommendations/jobs/${id}`, options),
  cancelJob: (id) => api.post(`/recommendations/jobs/${id}/cancel`, {}),
  // 同步兼容入口
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
  // Scoped mode accepts server-issued owned-result handles only.
  getResultCoverUrl: (item, scoped = false) => {
    if (!item) return ''
    if (!scoped)
      return item.cover_url
        ? recommendationApi.getCoverUrl(item.cover_url, item.source || 'jable')
        : ''
    if (typeof item.cover_handle !== 'string' || !item.cover_handle) return ''
    const base = api.defaults.baseURL.replace(/\/$/, '')
    return `${base}/recommendations/cover?handle=${encodeURIComponent(item.cover_handle)}`
  },
  // 获取推荐封面代理地址
  getCoverUrl: (coverUrl, source = 'jable') => {
    const base = api.defaults.baseURL.replace(/\/$/, '')
    return `${base}/recommendations/cover?url=${encodeURIComponent(coverUrl || '')}&source=${encodeURIComponent(source.toLowerCase())}`
  },
}
