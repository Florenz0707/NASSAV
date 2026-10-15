import { createRequestId } from '../../../shared/lib/requestId.js'
import { reactive, watch } from 'vue'
import { createAdminRead } from './adminRead.js'
const actions = new Set(['pause', 'resume', 'cancel', 'cleanup_retry'])
const reasons = new Set(['maintenance', 'security', 'user_request', 'quota_adjustment'])
export const workActionLabels = {
  pause: '暂停',
  resume: '恢复',
  cancel: '终止',
  cleanup_retry: '重试',
}

export function createWorkAdministration(
  api,
  currentOwner,
  { requestId = () => createRequestId() } = {}
) {
  const owner = currentOwner(),
    list = createAdminRead(api.list, currentOwner)
  const state = reactive({
    list,
    page: 1,
    page_size: 20,
    ordering: '-updated_at',
    editor: null,
    reason: 'maintenance',
    busy: false,
    confirming: false,
    error: '',
    message: '',
  })
  let active = true,
    command = null
  const owns = () => active && Boolean(owner) && currentOwner() === owner
  const stopOwner = watch(
    currentOwner,
    () => {
      if (!owns()) dispose()
    },
    { flush: 'sync' }
  )
  const load = () =>
    list.load({ page: state.page, page_size: state.page_size, ordering: state.ordering })
  function clear() {
    state.editor = null
    state.error = ''
    state.confirming = false
    command = null
  }
  function open(action, row) {
    if (!owns() || state.busy || !actions.has(action) || !row.allowed_actions?.includes(action))
      return
    clear()
    state.reason = 'maintenance'
    state.editor = { action, row: { ...row, allowed_actions: [...row.allowed_actions] } }
  }
  function setReason(value) {
    if (!state.busy) {
      state.reason = value
      command = null
      state.error = ''
    }
  }
  function close() {
    if (!state.busy) clear()
  }
  function prepare() {
    if (!owns() || !state.editor || state.busy) return
    state.error = ''
    if (!reasons.has(state.reason)) {
      state.error = '请选择操作原因'
      return
    }
    const { action, row } = state.editor
    command ||= {
      id: row.job_id,
      action,
      body: { expected_version: row.version, reason: state.reason, request_id: requestId() },
    }
    state.confirming = true
  }
  async function confirm() {
    if (!owns() || state.busy || !command) return
    const current = command
    state.confirming = false
    state.busy = true
    state.error = ''
    try {
      const response = await api.command(current)
      if (!owns()) return
      if (response.data?.job_id !== current.id) throw new Error('任务响应归属无效，可用原命令重试')
      state.message = '执行控制已登记；实际暂停、停止及文件清理以后台状态为准'
      clear()
      await load()
    } catch (error) {
      if (owns())
        state.error =
          (error.httpStatus || error.code) === 409
            ? '执行状态已变化，请关闭后刷新列表再确认。不会自动采用新版本执行。'
            : error.message || '操作未确认，可用原命令重试'
    } finally {
      if (owns()) state.busy = false
    }
  }
  function dispose() {
    active = false
    stopOwner()
    list.dispose()
    clear()
    state.busy = false
    state.message = ''
  }
  return Object.assign(state, {
    load,
    open,
    setReason,
    close,
    prepare,
    confirm,
    dispose,
    setConfirming: (value) => {
      state.confirming = Boolean(value)
    },
  })
}
