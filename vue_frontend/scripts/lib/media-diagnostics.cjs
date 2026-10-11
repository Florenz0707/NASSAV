// Test-only, bounded diagnostics. Never collect media URLs, cookies or response bodies.
async function installMediaDiagnostics(target) {
  await target.addInitScript(() => {
    const events = [],
      ids = new WeakMap()
    let serial = 0
    const ranges = (value) =>
      Array.from({ length: value.length }, (_, i) => [value.start(i), value.end(i)])
    const snapshot = (video) => {
      if (!ids.has(video)) ids.set(video, ++serial)
      return {
        element: ids.get(video),
        time: video.currentTime,
        duration: Number.isFinite(video.duration) ? video.duration : null,
        paused: video.paused,
        seeking: video.seeking,
        ready: video.readyState,
        network: video.networkState,
        frames: video.getVideoPlaybackQuality().totalVideoFrames,
        media_error: video.error?.code || null,
        buffered: ranges(video.buffered),
        seekable: ranges(video.seekable),
      }
    }
    const record = (video, event) => {
      events.push({ event, at_ms: Math.round(performance.now()), ...snapshot(video) })
      if (events.length > 100) events.shift()
    }
    for (const event of [
      'loadstart',
      'loadedmetadata',
      'canplay',
      'playing',
      'pause',
      'waiting',
      'seeking',
      'seeked',
      'error',
      'emptied',
    ]) {
      document.addEventListener(
        event,
        (e) => {
          if (e.target instanceof HTMLMediaElement) record(e.target, event)
        },
        true
      )
    }
    const original = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function (...args) {
      record(this, 'play-called')
      const result = original.apply(this, args)
      result.then(
        () => record(this, 'play-resolved'),
        (error) =>
          record(
            this,
            ['NotAllowedError', 'NotSupportedError', 'AbortError'].includes(error.name)
              ? `play-${error.name}`
              : 'play-rejected'
          )
      )
      return result
    }
    window.__nassavMediaDiagnostics = () => ({
      current: Array.from(document.querySelectorAll('video'), snapshot),
      alert_count: document.querySelectorAll('[role="alert"]').length,
      events,
    })
  })
}

async function readMediaDiagnostics(page) {
  return page?.evaluate(() => window.__nassavMediaDiagnostics?.()).catch(() => null)
}

module.exports = { installMediaDiagnostics, readMediaDiagnostics }
