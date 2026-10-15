import api from './client.js'

export const libraryApi = {
  listMemberships: (params) => api.get('/library/memberships', { params }),
  addEntry: (body) => api.post('/library/entries', body),
  releaseEntry: (id, body) =>
    api.delete(`/library/entries/${encodeURIComponent(id)}`, { data: body }),
  submitEntryOperation: (id, body) =>
    api.post(`/library/entries/${encodeURIComponent(id)}/operations`, body),
  listOperations: (params) => api.get('/my-operations', { params }),
  getOperation: (id) => api.get(`/my-operations/${encodeURIComponent(id)}`),
  cancelOperation: (id, payload) =>
    api.post(`/my-operations/${encodeURIComponent(id)}/cancel`, payload),
  membershipStatuses: (avids) => api.post('/library/entries/status', { avids }),
}
