// Pure editor lifecycle; the component supplies reactive state and explicit API/effects.
export function createPersonalResourceEditor({
  state,
  updateStatus,
  onUpdated = () => {},
  notify = () => {},
}) {
  let scope = '',
    generation = 0
  function reset() {
    generation++
    scope = ''
    Object.assign(state, {
      avid: '',
      version: 0,
      watched: false,
      isFavorite: false,
      notes: '',
      savedNotes: '',
      busy: '',
      error: '',
    })
  }
  function receive(snapshot, acceptDraft = false) {
    const version = snapshot.state_version ?? 0
    if (version < state.version) return false
    const dirty = state.notes !== state.savedNotes
    state.version = version
    state.watched = !!snapshot.watched
    state.isFavorite = !!snapshot.is_favorite
    state.savedNotes = snapshot.notes ?? ''
    if (!dirty || acceptDraft) state.notes = state.savedNotes
    return true
  }
  function sync(snapshot, owner) {
    if (!snapshot?.avid || !owner) {
      reset()
      return
    }
    const next = `${owner}:${snapshot.avid}`
    if (scope !== next) {
      reset()
      scope = next
      state.avid = snapshot.avid
    }
    receive(snapshot)
  }
  async function save(changes, action) {
    if (!scope || state.busy) return { ignored: true }
    if (typeof changes.notes === 'string' && changes.notes.length > 5000) {
      state.error = '备注最多5000字'
      return { success: false }
    }
    const ticket = generation,
      currentAvid = state.avid
    state.busy = action
    state.error = ''
    try {
      const response = await updateStatus(currentAvid, {
        ...changes,
        expected_version: state.version,
      })
      if (ticket !== generation) return { ignored: true }
      if (response.data?.avid !== currentAvid) throw new Error('服务器返回的个人状态不匹配，请重试')
      if (!receive(response.data, action === 'notes')) return { ignored: true }
      onUpdated(response.data)
      notify(action === 'notes' ? '备注已保存' : '个人状态已更新')
      return { success: true }
    } catch (error) {
      if (ticket !== generation) return { ignored: true }
      if (error.code === 409 && error.data?.avid === currentAvid) {
        if (receive(error.data)) onUpdated(error.data)
        state.error = '个人状态已在其他页面更新。备注草稿已保留，请确认后再次保存。'
      } else {
        state.error = error.message || '保存失败，请重试'
      }
      return { success: false }
    } finally {
      if (ticket === generation) state.busy = ''
    }
  }
  reset()
  return { sync, reset, save }
}
