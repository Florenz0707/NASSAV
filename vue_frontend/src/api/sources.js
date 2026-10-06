import api from './client.js'

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
