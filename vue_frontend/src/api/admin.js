import api from './client.js'

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
