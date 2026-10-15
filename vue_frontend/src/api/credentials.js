import api from './client.js'

export const personalCredentialApi = {
  list: () => api.get('/me/source-credentials'),
  create: (payload) => api.post('/me/source-credentials', payload),
  update: (id, payload) => api.put(`/me/source-credentials/${id}`, payload),
  revoke: (id, expectedVersion) =>
    api.delete(`/me/source-credentials/${id}`, { data: { expected_version: expectedVersion } }),
}
