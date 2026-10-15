import { reactive, watch } from 'vue'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'

const reasons = new Set(['maintenance', 'security', 'user_request', 'quota_adjustment'])
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
export const gcBlockerLabels = {
  admin_retention: '管理员保留',
  pool_not_pending_gc: '资源池尚未进入回收等待',
  version_not_reclaimable: '版本尚不可回收',
  grace_period: '宽限期未结束',
  memberships: '仍有用户持有',
  active_shared_work: '仍有共享工作',
  subscriptions: '仍有有效订阅',
  active_or_paused_task: '仍有活动或暂停任务',
  task_cleanup_pending: '任务清理尚未完成',
  writer_stop_unconfirmed: '尚未确认写入者停止',
  artifact_recovery_pending: '中间产物待恢复',
  read_leases: '仍有读取占用',
  playback_sessions: '仍有播放会话',
  other_gc_pending: '其他回收尚未收尾',
  version_grace_period: '版本宽限期未结束',
  unverified_versions: '存在未核验版本',
  legacy_assets_unmapped: '旧资产尚未映射',
}
export const gcBlockerLabel = (value) => gcBlockerLabels[value] || '其他保护条件（' + value + '）'

export function createResourceAdministration(
  api,
  currentOwner,
  canGc,
  applied,
  { requestId = () => crypto.randomUUID() } = {}
) {
  const owner = currentOwner(),
    guard = createRequestGuard()
  const state = reactive({
    editor: null,
    reason: 'maintenance',
    versionId: '',
    preview: null,
    previewLoading: false,
    busy: false,
    confirming: false,
    error: '',
    blockers: [],
    message: '',
  })
  let active = true,
    prepared = null,
    nonce = null
  const owns = () => active && Boolean(owner) && currentOwner() === owner
  const stopOwner = watch(
    currentOwner,
    () => {
      if (!owns()) dispose()
    },
    { flush: 'sync' }
  )
  function close() {
    if (state.busy) return
    clearEditor()
  }
  function clearEditor() {
    guard.invalidate()
    state.editor = state.preview = null
    state.error = ''
    state.blockers = []
    state.previewLoading = state.confirming = false
    prepared = nonce = null
  }
  function open(action, row) {
    if (
      !owns() ||
      state.busy ||
      !['preview', 'availability', 'retention', 'retry'].includes(action)
    )
      return
    close()
    state.reason = 'maintenance'
    state.versionId = ''
    state.editor = { action, row: { ...row } }
    if (action === 'preview') return loadPreview()
  }
  function setReason(value) {
    if (state.busy) return
    state.reason = value
    prepared = nonce = null
    state.error = ''
  }
  function setVersion(value) {
    if (state.busy) return
    guard.invalidate()
    state.versionId = value.trim()
    state.preview = null
    state.previewLoading = false
    state.error = ''
    prepared = nonce = null
  }
  async function loadPreview() {
    if (!owns() || state.busy || state.editor?.action !== 'preview') return
    state.error = ''
    if (state.versionId && !uuid.test(state.versionId)) {
      state.error = '请填写有效的版本 UUID，或留空预览整池'
      return
    }
    const ticket = guard.begin(),
      editor = state.editor,
      versionId = state.versionId.toLowerCase()
    state.preview = null
    state.previewLoading = true
    try {
      const response = await api.preview(editor.row.pool_id, versionId)
      if (!owns() || !guard.current(ticket)) return
      const result = response.data
      if (
        result?.pool_id !== editor.row.pool_id ||
        (result.version_id || '') !== versionId ||
        !Array.isArray(result.blockers) ||
        result.blockers.some((value) => typeof value !== 'string') ||
        typeof result.eligible !== 'boolean' ||
        result.eligible !== (result.blockers.length === 0)
      )
        throw new Error('回收预览归属无效')
      if (
        result.pool_version !== editor.row.pool_version ||
        result.pool_generation !== editor.row.generation
      )
        throw new Error('资源池版本已变化，请关闭后刷新列表再预览')
      state.preview = result
    } catch (error) {
      if (owns() && guard.current(ticket)) state.error = error.message || '无法获取回收预览'
    } finally {
      if (owns() && guard.current(ticket)) state.previewLoading = false
    }
  }
  function prepare() {
    if (!owns() || !state.editor || state.busy) return
    const { row, action } = state.editor
    state.error = ''
    state.blockers = []
    if (!reasons.has(state.reason)) {
      state.error = '请选择操作原因'
      return
    }
    const operation = action === 'preview' ? 'enqueue' : action
    if (['enqueue', 'retry'].includes(operation) && !canGc()) {
      state.error = '回收执行尚未开启，可先查看预览或设置保留'
      return
    }
    if (operation === 'enqueue' && (!state.preview?.eligible || state.previewLoading)) {
      state.error = '请先取得无阻塞的最新回收预览'
      return
    }
    const body = {
      reason: state.reason,
      expected_version: operation === 'retry' ? row.revision : row.pool_version,
    }
    if (operation === 'availability') body.available = !row.is_available
    if (operation === 'retention') body.retained = !row.retained
    if (operation === 'enqueue' && state.preview.version_id)
      body.version_id = state.preview.version_id
    nonce ||= requestId()
    prepared = {
      action: operation,
      id: operation === 'retry' ? row.job_id : row.pool_id,
      poolId: row.pool_id,
      body: { ...body, request_id: nonce },
    }
    state.confirming = true
  }
  async function confirm() {
    if (!owns() || state.busy || !prepared) return
    const command = prepared
    if (['enqueue', 'retry'].includes(command.action) && !canGc()) {
      state.confirming = false
      state.error = '回收执行尚未开启'
      return
    }
    state.confirming = false
    state.busy = true
    state.error = ''
    try {
      const response = await api.command(command)
      if (!owns()) return
      if (
        response.data?.pool_id !== command.poolId ||
        (command.action === 'retry' && response.data.job_id !== command.id)
      )
        throw new Error('管理响应归属无效，可用原命令重试')
      state.message = ['enqueue', 'retry'].includes(command.action)
        ? '回收请求已登记，文件处理结果以回收记录为准'
        : '资源管理操作已完成'
      clearEditor()
      await applied()
    } catch (error) {
      if (!owns()) return
      state.blockers = Array.isArray(error.data?.blockers) ? error.data.blockers : []
      state.error =
        error.data?.error_code === 'gc_not_enabled'
          ? '回收执行尚未开启'
          : (error.httpStatus || error.code) === 409
            ? '状态或保护条件已变化，未执行本次修改。请关闭后刷新确认。'
            : error.message || '操作未确认，可用原命令重试'
    } finally {
      if (owns()) state.busy = false
    }
  }
  function dispose() {
    active = false
    stopOwner()
    state.busy = false
    close()
    state.message = ''
  }
  return Object.assign(state, {
    open,
    close,
    setReason,
    setVersion,
    loadPreview,
    prepare,
    confirm,
    dispose,
    setConfirming: (value) => {
      state.confirming = Boolean(value)
    },
  })
}
