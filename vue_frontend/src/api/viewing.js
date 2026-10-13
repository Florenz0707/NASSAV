import api from './client.js'
export const viewingApi = {
  list: (kind, page = 1, pageSize = 15) =>
    api.get(`/personal/${kind}`, { params: { page, page_size: pageSize } }),
}
