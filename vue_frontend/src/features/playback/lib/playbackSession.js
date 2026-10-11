// Owns one UI operation. A late submit is still closed, never abandoned by aborting it.
export function createPlaybackSession({
  api,
  changed,
  uuid = () => crypto.randomUUID(),
  interval = 1000,
}) {
  let operation = 0,
    snapshot = null,
    timer = null,
    disposed = false,
    refreshUsed = false,
    refreshFlight = null
  const emit = (value) => {
    if (!disposed) changed(value)
  }
  async function closeRow(row) {
    if (!row || ['closed', 'failed'].includes(row.state)) return
    const command = uuid()
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        await api.close(row.session_id, row.version, command)
        return
      } catch (error) {
        if (error.httpStatus === 404 || error.httpStatus === 401) return
        if (attempt === 3) throw error
        row = (await api.status(row.session_id)).data
        if (['closed', 'failed'].includes(row.state)) return
      }
    }
  }
  async function stop(unloading = false) {
    const token = ++operation
    clearTimeout(timer)
    const old = snapshot
    snapshot = null
    try {
      if (unloading && old && api.closeOnLeave) await api.closeOnLeave(old)
      else await closeRow(old)
    } catch {
      if (token === operation) emit({ state: 'failed', message: '关闭未确认，会话将按期限回收' })
    }
  }
  function message(row) {
    if (row.state === 'failed')
      return row.error_code === 'media_identity_changed'
        ? '刷新后媒体不兼容，请重新开始播放'
        : row.error_code === 'expired'
          ? '播放会话已过期，请重试'
          : '准备播放失败，请重试'
    if (row.state === 'closed') return '播放会话已关闭'
    return ''
  }
  async function poll(token, id) {
    try {
      const row = (await api.status(id)).data
      if (disposed || token !== operation) return
      if (!snapshot || row.version >= snapshot.version) {
        if (
          snapshot?.state === 'ready' &&
          row.state === 'ready' &&
          snapshot.generation === row.generation
        )
          row.manifest_url = snapshot.manifest_url || row.manifest_url
        snapshot = row
        emit({ ...row, message: message(row) })
      }
      if (!['failed', 'closed'].includes(snapshot.state))
        timer = setTimeout(() => poll(token, id), snapshot.state === 'ready' ? 10000 : interval)
    } catch (error) {
      if (disposed || token !== operation) return
      emit({
        state: 'failed',
        message: error.httpStatus === 401 ? '登录已失效，请重新登录' : '读取播放状态失败，请重试',
      })
    }
  }
  async function start(avid) {
    const token = ++operation
    clearTimeout(timer)
    const old = snapshot
    snapshot = null
    try {
      await closeRow(old)
    } catch {
      if (token === operation) emit({ state: 'failed', message: '请先关闭已有播放会话后重试' })
      return
    }
    if (disposed || token !== operation) return
    refreshUsed = false
    emit({ state: 'queued', message: '' })
    try {
      const row = (await api.submit(avid, uuid())).data
      if (disposed || token !== operation) {
        await closeRow(row)
        return
      }
      snapshot = row
      emit({ ...row, message: message(row) })
      await poll(token, row.session_id)
    } catch (error) {
      if (disposed || token !== operation) return
      emit({
        state: 'failed',
        message:
          error.httpStatus === 404
            ? '在线播放未启用或资源已删除'
            : error.httpStatus === 409
              ? '播放会话已达上限，请先关闭其他播放器'
              : '无法准备播放，请重试',
      })
    }
  }
  async function refresh() {
    if (refreshFlight) return refreshFlight
    if (!snapshot || snapshot.state !== 'ready' || refreshUsed || disposed) return false
    refreshUsed = true
    const token = ++operation,
      id = snapshot.session_id,
      command = uuid()
    clearTimeout(timer)
    refreshFlight = (async () => {
      try {
        let row = (await api.status(id)).data
        if (disposed || token !== operation) return false
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            row = (await api.refresh(id, row.version, command)).data
            break
          } catch (error) {
            if (attempt === 2 || error.httpStatus !== 409) throw error
            row = (await api.status(id)).data
            if (disposed || token !== operation) return false
            if (row.refresh_count === 1 && ['queued', 'resolving', 'ready'].includes(row.state))
              break
          }
        }
        if (disposed || token !== operation) return false
        snapshot = row
        emit({ ...row, message: message(row) })
        await poll(token, id)
        return true
      } catch {
        if (token === operation && !disposed)
          emit({ state: 'failed', message: '无法刷新播放地址，请重新开始播放' })
        return false
      } finally {
        refreshFlight = null
      }
    })()
    return refreshFlight
  }
  return {
    start,
    refresh,
    stop,
    dispose() {
      disposed = true
      return stop()
    },
  }
}
