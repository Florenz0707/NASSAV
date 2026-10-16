import api from './client.js'
import { personalDataChanged } from '../shared/lib/personalDataEvents.js'
export const viewingApi = {
  list: (kind, page = 1, pageSize = 15) =>
    api.get(`/personal/${kind}`, { params: { page, page_size: pageSize } }),
  removeHistory: (entries) =>
    api
      .delete('/personal/history', { data: { entries } })
      .then((response) => personalDataChanged(response, ['history'])),
  removeWatched: () =>
    api
      .post('/personal/watch-later', { action: 'remove_watched' })
      .then((response) => personalDataChanged(response, ['watch-later'])),
}
