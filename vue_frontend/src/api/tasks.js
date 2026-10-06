import api from './client.js'

export const taskApi = {
  listJobs: (params) => api.get('/tasks/jobs', { params }),
  getJob: (id) => api.get(`/tasks/jobs/${id}`),
  controlJobs: (payload) => api.post('/tasks/jobs/actions', payload),
  // 获取任务队列状态
  getQueueStatus: () => api.get('/tasks/queue/status'),
}
