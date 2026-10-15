import api from './client.js'
import { sourceApi } from './sources.js'

export const adminApi = {
  listUsers: (params) => api.get('/admin/users', { params }),
  audit: () => api.get('/admin/audit'),
  accountCommand: (action, id, payload) => {
    if (action === 'create') return api.post('/admin/users', payload)
    if (action === 'update') return api.patch(`/admin/users/${encodeURIComponent(id)}`, payload)
    const routes = { revoke_sessions: 'revoke-sessions', reset_password: 'reset-password' }
    if (!routes[action]) return Promise.reject(new Error('不支持的账号操作'))
    return api.post(`/admin/users/${encodeURIComponent(id)}/${routes[action]}`, payload)
  },
}

export const systemCredentialApi = {
  list: () => api.get('/admin/source-credentials'),
  sources: sourceApi.getList,
  write: ({ id, source, revoke, body }) => {
    const path = '/admin/source-credentials'
    if (revoke) return api.delete(`${path}/${encodeURIComponent(id)}`, { data: body })
    return id
      ? api.put(`${path}/${encodeURIComponent(id)}`, body)
      : api.post(path, { source_name: source, ...body })
  },
}

export const resourceAdminApi = {
  pools: (params) => api.get('/admin/resource-pools', { params }),
  jobs: (params) => api.get('/admin/resource-gc-jobs', { params }),
  preview: (id, versionId) =>
    api.get(`/admin/resource-pools/${encodeURIComponent(id)}/gc-preview`, {
      params: versionId ? { version_id: versionId } : {},
    }),
  command: ({ action, id, body }) => {
    const key = encodeURIComponent(id)
    if (action === 'availability') return api.post(`/admin/resources/${key}/availability`, body)
    if (action === 'retention') return api.put(`/admin/resource-pools/${key}/retention`, body)
    if (action === 'enqueue') return api.post(`/admin/resource-pools/${key}/gc`, body)
    if (action === 'retry') return api.post(`/admin/resource-gc-jobs/${key}/retry`, body)
    return Promise.reject(new Error('不支持的资源管理操作'))
  },
}
