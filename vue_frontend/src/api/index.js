import axios from 'axios'

const api = axios.create({
    baseURL: '/nassav/api',
    timeout: 30000,
    headers: {
        'Content-Type': 'application/json'
    }
})

// 响应拦截器：兼容后端统一的 envelope 格式 {code, message, data}
api.interceptors.response.use(
    response => {
        const envelope = response.data
        if (response.status >= 200 && response.status < 300) {
            // 如果是后端的 envelope 格式
            if (envelope && typeof envelope.code !== 'undefined') {
                const c = envelope.code
                // 后端可能使用 code=0 或 HTTP 风格 code (200-299) 表示成功
                const success = (c === 0) || (typeof c === 'number' && c >= 200 && c < 300)
                if (success) {
                    const data = envelope.data
                    const pagination = envelope.pagination || (data && data.pagination) || null
                    return { code: envelope.code, message: envelope.message, data, pagination }
                }
                return Promise.reject({ httpStatus: response.status, code: envelope.code, message: envelope.message, data: envelope.data })
            }
            // 非 envelope（例如二进制文件响应）直接返回原始 response
            return response
        }
        return Promise.reject({ httpStatus: response.status, data: envelope })
    },
    error => {
        if (error.response) {
            const env = error.response.data
            if (env && typeof env.code !== 'undefined') {
                return Promise.reject({ httpStatus: error.response.status, code: env.code, message: env.message, data: env.data })
            }
            return Promise.reject({ httpStatus: error.response.status, data: env })
        }
        return Promise.reject({ code: 500, message: '网络错误', data: null })
    }
)

// 下载源管理（包含设置 Cookie）
export const sourceApi = {
    // 获取所有可用下载源列表
    getList: () => api.get('/source/list'),
    // 设置或自动获取 Cookie
    setCookie: (payload) => api.post('/source/cookie', payload)
}

// 资源管理
export const resourceApi = {
    // 获取所有已保存资源列表（推荐使用新的 /resources/ 统一入口）
    getList: (params = {}) => api.get('/resources/', { params }),

    // 获取资源元数据
    getMetadata: (avid) => api.get('/resource/metadata', {params: {avid}}),

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
                try { URL.revokeObjectURL(firstUrl) } catch (e) {}
                resourceApi._coverCache.delete(firstKey)
            }
            return obj
        } catch (e) {
            // fallback to URL
            return `${api.defaults.baseURL.replace(/\/$/, '')}/resource/cover?avid=${encodeURIComponent(avid)}`
        }
    },
    // 明确撤销并删除缓存项
    revokeCoverObjectUrl: (avid) => {
        if (resourceApi._coverCache.has(avid)) {
            const url = resourceApi._coverCache.get(avid)
            try { URL.revokeObjectURL(url) } catch (e) {}
            resourceApi._coverCache.delete(avid)
        }
    },

    // 添加新资源
    addNew: (avid, source = 'any') => api.post('/resource', {avid, source}),

    // 刷新资源
    refresh: (avid) => api.post(`/resource/refresh/${encodeURIComponent(avid)}`),

    // 删除资源
    delete: (avid) => api.delete(`/resource/${encodeURIComponent(avid)}`)
    ,
    // 批量操作：body 应包含 { action: 'delete'|'refresh'|'add' , avids: [] } 或自定义格式
    batch: (payload) => api.post('/resources/batch', payload)
}

// 下载管理
export const downloadApi = {
    // 获取已下载视频列表
    getList: () => api.get('/downloads/list'),

    // 获取视频文件路径
    getFilePath: (avid) => api.get('/downloads/abspath', {params: {avid}}),

    // 提交下载任务
    submitDownload: (avid) => api.post(`/downloads/${encodeURIComponent(avid)}`),

    // 删除下载的视频
    deleteFile: (avid) => api.delete(`/downloads/${encodeURIComponent(avid)}`),
    // 批量提交下载任务
    batchSubmit: (avids) => api.post('/downloads/batch_submit', { avids })
}

// 任务管理
export const taskApi = {
    // 获取任务队列状态
    getQueueStatus: () => api.get('/tasks/queue/status')
}
