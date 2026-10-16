import { createRequestId } from '../shared/lib/requestId.js'
import api, { browserContextHeaders } from './client.js'
import { personalDataChanged } from '../shared/lib/personalDataEvents.js'

export const playbackApi = {
  viewed: (id, generation, sequence) =>
    api
      .post(`/playback-sessions/${id}/viewed`, { session_generation: generation, sequence })
      .then((response) => personalDataChanged(response, ['history'])),
  continuations: (limit = 6) => api.get('/playback-progress', { params: { limit } }),
  progress: (id) => api.get(`/playback-sessions/${id}/progress`),
  claimProgress: (id, body) => api.post(`/playback-sessions/${id}/progress/claim`, body),
  saveProgress: (id, body) => api.put(`/playback-sessions/${id}/progress`, body),
  clearProgress: (avid) => api.delete(`/resources/${encodeURIComponent(avid)}/playback-progress`),
  saveProgressOnLeave: async (id, body) => {
    const csrf = document.cookie
      .split('; ')
      .find((value) => value.startsWith('csrftoken='))
      ?.slice(10)
    const response = await fetch(`/nassav/api/playback-sessions/${id}/progress`, {
      method: 'PUT',
      credentials: 'same-origin',
      keepalive: true,
      headers: {
        ...browserContextHeaders(),
        'Content-Type': 'application/json',
        'X-CSRFToken': decodeURIComponent(csrf || ''),
      },
      body: JSON.stringify(body),
    })
    if (!response.ok)
      throw Object.assign(new Error('Progress save failed'), { httpStatus: response.status })
    return response.json()
  },
  submit: (avid, requestId, mode = 'source') =>
    api.post(`/resources/${encodeURIComponent(avid)}/playback-sessions`, {
      request_id: requestId,
      mode,
    }),
  status: (id) => api.get(`/playback-sessions/${id}`),
  refresh: (id, version, requestId) =>
    api.post(`/playback-sessions/${id}/refresh`, {
      expected_version: version,
      request_id: requestId,
    }),
  closeOnLeave: (row) => {
    const csrf = document.cookie
      .split('; ')
      .find((value) => value.startsWith('csrftoken='))
      ?.slice(10)
    return fetch(`/nassav/api/playback-sessions/${row.session_id}/close`, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: true,
      headers: {
        ...browserContextHeaders(),
        'Content-Type': 'application/json',
        'X-CSRFToken': decodeURIComponent(csrf || ''),
      },
      body: JSON.stringify({ expected_version: row.version, request_id: createRequestId() }),
    }).catch(() => {})
  },
  close: (id, version, requestId) =>
    api.post(`/playback-sessions/${id}/close`, {
      expected_version: version,
      request_id: requestId,
    }),
}
