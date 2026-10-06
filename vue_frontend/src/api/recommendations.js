import api, { RECOMMENDATION_REQUEST_TIMEOUT } from './client.js'

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
