import api from './client.js'

export const playbackApi = {
  submit: (avid, requestId) =>
    api.post(`/resources/${encodeURIComponent(avid)}/playback-sessions`, { request_id: requestId }),
  status: (id) => api.get(`/playback-sessions/${id}`),
  close: (id, version, requestId) =>
    api.post(`/playback-sessions/${id}/close`, {
      expected_version: version,
      request_id: requestId,
    }),
}
