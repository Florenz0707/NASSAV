// Prefer the validated MSE engine; fall back to native HLS when MSE is unavailable.
export async function attachPlayer(
  video,
  url,
  { failed, position = 0, resume = false, current = () => true, mediaType = 'hls' }
) {
  if (!url.startsWith('/nassav/api/playback-sessions/')) throw new Error('Invalid media entry')
  let hls = null,
    destroyed = false
  const restore = () => {
    if (position > 0 && Number.isFinite(video.duration) && position < video.duration)
      video.currentTime = position
    if (resume) video.play().catch(() => {})
  }
  const nativeError = () => {
    if (!destroyed) failed('浏览器无法播放此视频，请重试')
  }
  const destroy = () => {
    if (destroyed) return
    destroyed = true
    video.removeEventListener('loadedmetadata', restore)
    video.removeEventListener('error', nativeError)
    hls?.destroy()
    video.pause()
    video.removeAttribute('src')
    video.load()
  }
  video.addEventListener('loadedmetadata', restore, { once: true })
  try {
    if (!current()) {
      destroy()
      return destroy
    }
    if (mediaType === 'mp4') {
      video.addEventListener('error', nativeError)
      video.src = url
      return destroy
    }
    if (mediaType !== 'hls') throw new Error('Unsupported media type')
    const { default: Hls } = await import('hls.js')
    if (!current()) {
      destroy()
      return destroy
    }
    if (!Hls.isSupported()) {
      if (!video.canPlayType('application/vnd.apple.mpegurl'))
        throw new Error('Unsupported browser')
      video.addEventListener('error', nativeError)
      video.src = url
    } else {
      const loadPolicies = {}
      for (const name of [
        'fragLoadPolicy',
        'keyLoadPolicy',
        'playlistLoadPolicy',
        'manifestLoadPolicy',
      ]) {
        const policy = Hls.DefaultConfig[name].default
        loadPolicies[name] = {
          default: {
            ...policy,
            errorRetry: policy.errorRetry && {
              ...policy.errorRetry,
              shouldRetry: (_config, _count, _timeout, response, retry) =>
                response?.code === 410 ? false : retry,
            },
          },
        }
      }
      hls = new Hls({
        maxBufferLength: 30,
        maxMaxBufferLength: 60,
        backBufferLength: 30,
        maxBufferSize: 8 * 1024 * 1024,
        ...loadPolicies,
      })
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (
          !destroyed &&
          (data.fatal ||
            (data.type === Hls.ErrorTypes.NETWORK_ERROR && data.response?.code === 410))
        ) {
          hls.stopLoad()
          failed(
            data.type === Hls.ErrorTypes.NETWORK_ERROR
              ? '视频读取失败，请重试'
              : '当前浏览器无法解码此视频',
            data.response?.code || 0
          )
        }
      })
      hls.attachMedia(video)
      hls.loadSource(url)
    }
    return destroy
  } catch (error) {
    destroy()
    throw error
  }
}
