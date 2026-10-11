// Native HLS first; hls.js is loaded only when the browser needs MSE.
export async function attachPlayer(video, url, { failed, position = 0, current = () => true }) {
  if (!url.startsWith('/nassav/api/playback-sessions/')) throw new Error('Invalid media entry')
  let hls = null,
    destroyed = false
  const restore = () => {
    if (position > 0 && Number.isFinite(video.duration) && position < video.duration)
      video.currentTime = position
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
  video.addEventListener('loadedmetadata', restore)
  try {
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.addEventListener('error', nativeError)
      video.src = url
    } else {
      const { default: Hls } = await import('hls.js')
      if (!current()) {
        destroy()
        return destroy
      }
      if (!Hls.isSupported()) throw new Error('Unsupported browser')
      hls = new Hls({ maxBufferLength: 30, maxMaxBufferLength: 60, backBufferLength: 30 })
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal && !destroyed) {
          hls.stopLoad()
          failed(
            data.type === Hls.ErrorTypes.NETWORK_ERROR
              ? '视频读取失败，请重试'
              : '当前浏览器无法解码此视频'
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
