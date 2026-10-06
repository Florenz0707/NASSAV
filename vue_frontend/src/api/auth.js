import api from './client.js'

export const authApi = {
  getSession: () => api.get('/auth/session'),
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
}
