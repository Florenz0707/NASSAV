import { createProgressDrafts } from './progressDrafts.js'
// Progress owns event subscriptions, writer tokens and one serial save queue.
export function createPlaybackProgress({
  api,
  changed = () => {},
  uuid = () => crypto.randomUUID(),
  now = () => Date.now(),
  drafts = createProgressDrafts(),
}) {
  let current = null
  const emit = (ctx, value) => {
    if (current === ctx) changed(value)
  }
  function sample(ctx) {
    const video = ctx.video
    if (
      !ctx.started ||
      ctx.restoring ||
      !Number.isFinite(video.duration) ||
      video.duration <= 0 ||
      !Number.isFinite(video.currentTime)
    )
      return null
    return {
      position_seconds: Math.max(0, Math.min(video.currentTime, video.duration)),
      duration_seconds: video.duration,
      completed: video.ended,
    }
  }
  async function acquire(ctx) {
    if (ctx.token || ctx.blocked || ctx.detached) return
    if (ctx.claiming) return ctx.claiming
    ctx.claiming = (async () => {
      try {
        const data = (
          await api.claimProgress(ctx.row.session_id, {
            session_generation: ctx.row.generation,
            expected_writer_generation: ctx.saved.writer_generation,
            request_id: ctx.claimId,
          })
        ).data
        ctx.token = data
        emit(ctx, { candidate: null, message: '' })
      } catch (error) {
        if ([401, 404, 409, 410].includes(error.httpStatus)) ctx.blocked = true
        emit(ctx, {
          candidate: null,
          message: ctx.blocked
            ? '进度保存权已失效；本页仍可播放'
            : '暂时无法保存进度，播放不受影响',
        })
      } finally {
        ctx.claiming = null
      }
    })()
    return ctx.claiming
  }
  async function drain(ctx, leaving = false) {
    if (ctx.flight) {
      await ctx.flight
      return drain(ctx, leaving)
    }
    if (ctx.blocked || !ctx.started) return
    await ctx.loading
    ctx.lastSaved = now()
    await acquire(ctx)
    if (ctx.flight) {
      await ctx.flight
      return drain(ctx, leaving)
    }
    if (!ctx.token || (!ctx.pending && !ctx.retry)) return
    const body = ctx.retry || {
      session_generation: ctx.row.generation,
      writer_generation: ctx.token.writer_generation,
      sequence: ++ctx.sequence,
      expected_version: ctx.token.version,
      request_id: uuid(),
      ...ctx.pending,
    }
    drafts.put(ctx.token, body)
    if (!ctx.retry) ctx.pending = null
    ctx.retry = body
    ctx.flight = (async () => {
      try {
        const method =
          leaving && api.saveProgressOnLeave ? api.saveProgressOnLeave : api.saveProgress
        ctx.lastSaved = now()
        ctx.token = (await method(ctx.row.session_id, body)).data
        drafts.remove(ctx.token, body)
        ctx.retry = null
        ctx.lastSaved = now()
        emit(ctx, { candidate: null, message: '' })
      } catch (error) {
        if ([401, 404, 409, 410].includes(error.httpStatus)) {
          ctx.blocked = true
          ctx.retry = null
        }
        emit(ctx, {
          candidate: null,
          message: ctx.blocked
            ? '进度保存权已失效；本页仍可播放'
            : '进度尚未保存，将在下次播放事件重试',
        })
      } finally {
        ctx.flight = null
      }
    })()
    await ctx.flight
    if (!ctx.retry && ctx.pending && !ctx.blocked) return drain(ctx, leaving)
  }
  function flush(ctx, leaving = false) {
    const value = sample(ctx)
    if (value) ctx.pending = value
    return drain(ctx, leaving)
  }
  function restoreCandidate(ctx) {
    if (ctx.started || ctx.chosen || !ctx.saved || !Number.isFinite(ctx.video.duration)) return
    const saved = ctx.candidate || ctx.saved
    // Do not jump into the final seconds or apply an incompatible duration.
    if (
      !saved.completed &&
      saved.position_seconds > 5 &&
      saved.position_seconds < ctx.video.duration - 5 &&
      Math.abs(saved.duration_seconds - ctx.video.duration) <=
        Math.max(2, ctx.video.duration * 0.01)
    ) {
      emit(ctx, { candidate: saved, message: '' })
    }
  }
  function bind(row, video) {
    detach()
    const ctx = {
      row,
      video,
      token: null,
      saved: null,
      started: false,
      blocked: false,
      restoring: false,
      chosen: row.refresh_count === 1,
      sequence: 0,
      pending: null,
      retry: null,
      flight: null,
      claiming: null,
      claimId: uuid(),
      lastSaved: now(),
      handlers: {},
    }
    current = ctx
    changed({ candidate: null, message: '' })
    ctx.loading = api
      .progress(row.session_id)
      .then(({ data }) => {
        ctx.saved = data
        ctx.candidate = drafts.get(data) || data
        restoreCandidate(ctx)
      })
      .catch(() => {
        ctx.blocked = true
        emit(ctx, { candidate: null, message: '无法读取播放进度，本次仍可播放' })
      })
    ctx.handlers.loadedmetadata = () => restoreCandidate(ctx)
    ctx.handlers.play = () => {
      ctx.started = true
      if (!ctx.blocked) emit(ctx, { candidate: null, message: '' })
      void flush(ctx)
    }
    ctx.handlers.timeupdate = () => {
      if (now() - ctx.lastSaved >= 15000) void flush(ctx)
    }
    for (const name of ['pause', 'seeked', 'ended'])
      ctx.handlers[name] = () => {
        void flush(ctx)
      }
    for (const [name, handler] of Object.entries(ctx.handlers))
      video.addEventListener(name, handler)
    return ctx.loading
  }
  async function choose(resume) {
    const ctx = current
    if (!ctx || ctx.blocked) return
    await ctx.loading
    if (current !== ctx) return
    ctx.chosen = true
    ctx.restoring = true
    emit(ctx, { candidate: null, message: '' })
    const position = resume ? (ctx.candidate || ctx.saved).position_seconds : 0
    if (Number.isFinite(ctx.video.duration))
      ctx.video.currentTime = Math.min(position, Math.max(0, ctx.video.duration - 0.1))
    ctx.restoring = false
    try {
      await ctx.video.play()
    } catch {
      emit(ctx, { candidate: null, message: '请点击播放器开始播放' })
    }
  }
  function detach(leaving = false) {
    const ctx = current
    if (!ctx) return Promise.resolve()
    for (const [name, handler] of Object.entries(ctx.handlers))
      ctx.video.removeEventListener(name, handler)
    const value = sample(ctx)
    ctx.detached = true
    current = null
    if (leaving && value && ctx.token && !ctx.blocked && !ctx.flight && api.saveProgressOnLeave) {
      const body = {
        ...(ctx.retry || {
          session_generation: ctx.row.generation,
          writer_generation: ctx.token.writer_generation,
          sequence: ++ctx.sequence,
          expected_version: ctx.token.version,
          request_id: uuid(),
          ...value,
        }),
        close_after_save: true,
      }
      drafts.put(ctx.token, body)
      const pending = api
        .saveProgressOnLeave(ctx.row.session_id, body)
        .then(({ data }) => {
          if (data.saved !== false) drafts.remove(data, body)
        })
        .catch(() => {})
      pending.closesSession = true
      return pending
    }
    if (leaving) {
      if (value && ctx.token)
        drafts.put(ctx.token, {
          ...value,
          writer_generation: ctx.token.writer_generation,
          sequence: ctx.sequence + 1,
          expected_version: ctx.token.version,
        })
      ctx.blocked = true
      return ctx.flight || Promise.resolve()
    }
    return flush(ctx)
  }

  return {
    bind,
    choose,
    detach,
    flush: (leaving = false) => (current ? flush(current, leaving) : Promise.resolve()),
  }
}
