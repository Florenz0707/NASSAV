import { createQueryCache } from '../shared/lib/queryCache.js'
import api, { requestCacheIdentity } from './client.js'
const cache = createQueryCache({ ttl: 300000, limit: 8 })

export const sourceApi = {
  getSearchCapabilities: () =>
    cache.read(`${requestCacheIdentity()}:capabilities`, () =>
      api.get('/source/search-capabilities')
    ),
  // 获取所有可用下载源列表
  getList: () => cache.read(`${requestCacheIdentity()}:list`, () => api.get('/source/list')),
  // 获取所有已设置的源 Cookie 列表
  getCookies: () => api.get('/source/cookie', { headers: { 'Cache-Control': 'no-store' } }),
  // 设置或自动获取 Cookie
  setCookie: (payload) => api.post('/source/cookie', payload),
  // 删除指定源的 Cookie
  deleteCookie: (source) => api.delete('/source/cookie', { params: { source } }),
}
