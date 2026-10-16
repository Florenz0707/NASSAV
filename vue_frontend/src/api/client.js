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
  },
})

export const RECOMMENDATION_REQUEST_TIMEOUT = 120000
// Five source pages can each spend 60s in the browser plus direct/control work.
export const EXTERNAL_SEARCH_REQUEST_TIMEOUT = 450000
let browserContext = ''
export function setBrowserContext(value = '') {
  browserContext = typeof value === 'string' ? value : ''
}
export function browserContextHeaders() {
  return browserContext ? { 'X-NASSAV-Context': browserContext } : {}
}
export function contextualImageUrl(url) {
  if (!browserContext) return url
  const hash = url.indexOf('#')
  const path = hash < 0 ? url : url.slice(0, hash)
  const fragment = hash < 0 ? '' : url.slice(hash)
  const query = path.indexOf('?')
  const base = query < 0 ? path : path.slice(0, query)
  const params = new URLSearchParams(query < 0 ? '' : path.slice(query + 1))
  params.delete('_context')
  params.append('_context', browserContext)
  return `${base}?${params}${fragment}`
}
let sessionGeneration = 0
export const requestCacheIdentity = () => sessionGeneration
export function invalidateSessionRequests() {
  sessionGeneration++
}
const sessionChanged = () => ({
  code: 'session_changed',
  message: '请求上下文已变化，请重试',
  data: null,
})
const belongsToSession = (config) => config?._nassavSessionGeneration === sessionGeneration
api.interceptors.request.use(
  (config) => {
    config._nassavSessionGeneration = sessionGeneration
    Object.assign(config.headers, browserContextHeaders())
    return config
  },
  undefined,
  { synchronous: true }
)
const contextListeners = new Set()
export function onBrowserContextChanged(listener) {
  contextListeners.add(listener)
  return () => contextListeners.delete(listener)
}
const unauthorizedListeners = new Set()

export function onUnauthorized(listener) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function reportUnauthorized(error) {
  if (
    !belongsToSession(error.config) ||
    error.response?.status !== 401 ||
    error.config?.url === '/auth/login'
  )
    return
  for (const listener of unauthorizedListeners) listener()
}

// 响应拦截器：兼容后端统一的 envelope 格式 {code, message, data}
api.interceptors.response.use(
  (response) => {
    if (!belongsToSession(response.config)) return Promise.reject(sessionChanged())
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
    if (!belongsToSession(error.config)) return Promise.reject(sessionChanged())
    reportUnauthorized(error)
    if (
      error.response?.status === 409 &&
      error.response?.data?.data?.error_code === 'browser_context_changed'
    ) {
      for (const listener of contextListeners) listener()
    }
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
