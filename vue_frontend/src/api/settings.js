import api from './client.js'

export const settingsApi = {
  // 获取用户设置
  get: () => api.get('/setting'),
  // 更新用户设置（支持部分更新）
  update: (payload) => api.put('/setting', payload),
}
