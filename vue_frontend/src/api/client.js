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

export const RECOMMENDATION_REQUEST_TIMEOUT = 120000
// Five source pages can each spend 60s in the browser plus direct/control work.
export const EXTERNAL_SEARCH_REQUEST_TIMEOUT = 450000
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

export default api
