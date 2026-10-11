import api from './client.js'

export const playbackApi = {
  submit: (avid, requestId) =>
    api.post(`/resources/${encodeURIComponent(avid)}/playback-sessions`, { request_id: requestId }),
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
        'Content-Type': 'application/json',
        'X-CSRFToken': decodeURIComponent(csrf || ''),
      },
      body: JSON.stringify({ expected_version: row.version, request_id: crypto.randomUUID() }),
    }).catch(() => {})
  },
  close: (id, version, requestId) =>
    api.post(`/playback-sessions/${id}/close`, {
      expected_version: version,
      request_id: requestId,
    }),
}
