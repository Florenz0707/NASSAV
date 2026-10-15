import api from './client.js'

export const libraryApi = {
  membershipStatuses: (avids) => api.post('/library/entries/status', { avids }),
}
