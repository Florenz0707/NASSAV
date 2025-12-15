import axios from 'axios'

const api = axios.create({
  baseURL: '/nassav/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 响应拦截器
api.interceptors.response.use(
  response => {
    const { code, message, data } = response.data
    if (code >= 200 && code < 300) {
      return { code, message, data }
    }
    return Promise.reject({ code, message, data })
  },
  error => {
    if (error.response) {
      return Promise.reject(error.response.data)
    }
    return Promise.reject({ code: 500, message: '网络错误', data: null })
  }
)

// 下载源管理
export const sourceApi = {
  // 获取所有可用下载源列表
  getList: () => api.get('/source/list')
}

// 资源管理
export const resourceApi = {
  // 获取所有已保存资源列表
  getList: () => api.get('/resource/list'),

  // 获取资源元数据
  getMetadata: (avid) => api.get('/resource/metadata', { params: { avid } }),

  // 获取封面图片URL
  getCoverUrl: (avid) => `/nassav/api/resource/cover?avid=${encodeURIComponent(avid)}`,

  // 添加新资源
  addNew: (avid, source = 'any') => api.post('/resource/new', { avid, source }),

  // 刷新资源
  refresh: (avid) => api.post('/resource/refresh', { avid })
}

// 下载管理
export const downloadApi = {
  // 获取已下载视频列表
  getList: () => api.get('/downloads/list'),

  // 提交下载任务
  submitDownload: (avid) => api.post('/downloads/new', { avid })
}

export default api
