import api from './client.js'

export const externalSearchApi = {
  submit: (query, signal) => api.post('/search/jobs', query, { signal }),
  getJob: (taskId, token, signal, pagination = {}) =>
    api.get(`/search/jobs/${taskId}`, { params: { token, ...pagination }, signal }),
  cancelJob: (taskId, token) => api.post(`/search/jobs/${taskId}/cancel`, { token }),
}
