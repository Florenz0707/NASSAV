// Native media changes use one debounced, serial preference writer per player.
export function bindPlaybackPreferences(
  video,
  { preferences, save, current = () => true, failed = () => {}, delay = 500 }
) {
  let disposed = false,
    finalizing = false,
    timer = null,
    flight = null,
    pending = null
  let saved = { volume: preferences.volume, muted: preferences.muted, rate: preferences.rate }
  video.volume = saved.volume
  video.muted = saved.muted
  video.defaultPlaybackRate = saved.rate
  video.playbackRate = saved.rate
  const sample = () => ({
    volume: Math.round(video.volume * 100) / 100,
    muted: video.muted,
    rate: video.playbackRate,
  })
  async function flush() {
    if (flight || !pending || (!current() && !finalizing)) return
    const patch = Object.fromEntries(
      Object.entries(pending).filter(([key, value]) => value !== saved[key])
    )
    pending = null
    if (!Object.keys(patch).length) return
    flight = Promise.resolve().then(() => save(patch))
    try {
      await flight
      saved = { ...saved, ...patch }
    } catch {
      if (!disposed && current()) failed()
    } finally {
      flight = null
    }
    if ((!disposed || finalizing) && pending) await flush()
  }
  function changed() {
    if (disposed || !current()) return
    pending = sample()
    clearTimeout(timer)
    timer = setTimeout(() => {
      void flush()
    }, delay)
  }
  video.addEventListener('volumechange', changed)
  video.addEventListener('ratechange', changed)
  return () => {
    if (disposed) return
    clearTimeout(timer)
    video.removeEventListener('volumechange', changed)
    video.removeEventListener('ratechange', changed)
    finalizing = current()
    // Submit a real user change before teardown; initialization is always a no-op.
    void flush()
    disposed = true
  }
}

export function playbackMode(explicit, preferred, hasVideo) {
  if (['local', 'source'].includes(explicit)) return explicit
  return preferred === 'auto' ? (hasVideo ? 'local' : 'source') : preferred
}
