// Only real playing events record history. Play/resume starts a new episode;
// buffering and retries keep the same monotonically increasing sequence.
export function createViewingRecorder({ record, changed = () => {} }) {
  let current = null,
    previousId = '',
    previousSequence = 0
  function detach() {
    if (current) {
      current.video.removeEventListener('play', current.play)
      current.video.removeEventListener('playing', current.playing)
      previousId = current.row.session_id
      previousSequence = current.sequence
    }
    current = null
    changed('')
  }
  async function send(ctx) {
    if (current !== ctx || !ctx.started || ctx.saved >= ctx.sequence || ctx.pending) return
    const sequence = ctx.sequence
    ctx.pending = true
    try {
      await record(ctx.row.session_id, ctx.row.generation, sequence)
      if (current === ctx) {
        ctx.saved = sequence
        changed('')
      }
    } catch {
      if (current === ctx) changed('观看历史保存失败，请重试')
    } finally {
      ctx.pending = false
      if (current === ctx && ctx.sequence > sequence) void send(ctx)
    }
  }
  function bind(row, video) {
    detach()
    const sequence = Math.max(
      row.history_sequence || 0,
      previousId === row.session_id ? previousSequence : 0
    )
    const ctx = {
      row: { ...row },
      video,
      sequence,
      started: false,
      saved: sequence,
      pending: false,
    }
    ctx.play = () => {
      ctx.sequence++
      ctx.started = false
    }
    ctx.playing = () => {
      if (ctx.sequence === ctx.saved) return
      ctx.started = true
      void send(ctx)
    }
    current = ctx
    video.addEventListener('play', ctx.play)
    video.addEventListener('playing', ctx.playing)
  }
  return { bind, detach, retry: () => current && send(current) }
}
