import { reactive, watch } from 'vue'
import { createAdminRead } from './adminRead.js'

const GIB = 1024 ** 3
const reasons = new Set(['security', 'maintenance', 'user_request', 'quota_adjustment'])
const defaults = () => ({
  username: '',
  password: '',
  role: 'user',
  is_active: true,
  unlimited: true,
  quota: '',
  operations: '2',
  reason: 'maintenance',
})

export function createAccountAdministration(
  api,
  currentOwner,
  { requestId = () => crypto.randomUUID() } = {}
) {
  const owner = currentOwner(),
    list = createAdminRead(api.listUsers, currentOwner)
  const state = reactive({
    list,
    page: 1,
    page_size: 20,
    editor: null,
    draft: defaults(),
    dirty: false,
    busy: false,
    error: '',
    message: '',
    fieldErrors: {},
    confirming: false,
    discarding: false,
  })
  let active = true,
    nonce = null,
    prepared = null
  const owns = () => active && Boolean(owner) && currentOwner() === owner
  const stopDraft = watch(
    () => state.draft,
    () => {
      if (state.editor && !state.busy) {
        state.dirty = true
        nonce = null
        prepared = null
        state.error = ''
        state.fieldErrors = {}
      }
    },
    { deep: true, flush: 'sync' }
  )
  const stopOwner = watch(
    currentOwner,
    () => {
      if (!owns()) dispose()
    },
    { flush: 'sync' }
  )
  function setField(key, value) {
    if (owns() && !state.busy && Object.hasOwn(state.draft, key)) state.draft[key] = value
  }
  function setConfirming(value) {
    state.confirming = Boolean(value)
  }
  function setDiscarding(value) {
    state.discarding = Boolean(value)
  }
  function load() {
    return list.load({ page: state.page, page_size: state.page_size })
  }
  function open(action, account = null) {
    if (!owns() || state.busy) return
    state.editor = null
    const draft = defaults()
    if (account)
      Object.assign(draft, {
        username: account.username,
        role: account.role,
        is_active: account.is_active,
        unlimited: account.storage_quota_bytes === null,
        quota:
          account.storage_quota_bytes === null ? '' : String(account.storage_quota_bytes / GIB),
        operations: String(account.max_active_operations),
      })
    if (['create', 'reset_password'].includes(action)) draft.reason = 'user_request'
    if (action === 'revoke_sessions') draft.reason = 'security'
    state.draft = draft
    state.editor = { action, account: account ? { ...account } : null }
    state.dirty = false
    state.error = ''
    state.fieldErrors = {}
    state.confirming = state.discarding = false
    nonce = prepared = null
  }
  function clearEditor() {
    state.editor = null
    state.draft = defaults()
    state.dirty = false
    state.confirming = state.discarding = false
    state.error = ''
    state.fieldErrors = {}
    nonce = prepared = null
  }
  function close() {
    if (state.busy) return
    if (state.dirty) state.discarding = true
    else clearEditor()
  }
  function prepare() {
    if (!owns() || !state.editor || state.busy) return
    state.error = ''
    const { action, account } = state.editor,
      draft = state.draft,
      errors = {}
    const body = { reason: draft.reason }
    if (!reasons.has(draft.reason)) errors.reason = '请选择操作原因'
    if (action === 'create') {
      const username = draft.username.trim()
      if (!username || username.length > 150) errors.username = '填写1至150字的用户名'
      Object.assign(body, { username, role: draft.role, is_active: draft.is_active })
    } else body.expected_version = account.version
    if (['create', 'reset_password'].includes(action)) {
      if (draft.password.length < 12 || draft.password.length > 256)
        errors.password = '密码长度需为12至256个字符'
      body.password = draft.password
    }
    if (action === 'update') {
      if (draft.role !== account.role) body.role = draft.role
      if (draft.is_active !== account.is_active) body.is_active = draft.is_active
      const originalQuota =
        account.storage_quota_bytes === null ? '' : String(account.storage_quota_bytes / GIB)
      if (
        draft.unlimited !== (account.storage_quota_bytes === null) ||
        (!draft.unlimited && draft.quota !== originalQuota)
      ) {
        if (draft.unlimited) body.storage_quota_bytes = null
        else {
          const numeric = typeof draft.quota === 'string' || typeof draft.quota === 'number'
          const bytes =
            numeric && String(draft.quota).trim() ? Math.floor(Number(draft.quota) * GIB) : NaN
          if (!Number.isSafeInteger(bytes) || bytes < 0)
            errors.quota = '填写有效的非负GiB数值，且不超过安全整数范围'
          else if (bytes !== account.storage_quota_bytes) body.storage_quota_bytes = bytes
        }
      }
      if (draft.operations !== String(account.max_active_operations)) {
        const valid =
          (typeof draft.operations === 'string' && /^\d+$/.test(draft.operations)) ||
          typeof draft.operations === 'number'
        const operations = valid ? Number(draft.operations) : NaN
        if (!Number.isInteger(operations) || operations < 1 || operations > 2147483647)
          errors.operations = '活动请求上限需为1至2147483647的整数'
        else if (operations !== account.max_active_operations)
          body.max_active_operations = operations
      }
      if (Object.keys(body).length === 2 && !Object.keys(errors).length)
        state.error = '尚未修改账号配置'
    }
    state.fieldErrors = errors
    if (Object.keys(errors).length || state.error) return
    nonce ||= requestId()
    prepared = { action, userId: account?.user_id || null, body: { ...body, request_id: nonce } }
    state.confirming = true
  }
  async function confirm() {
    if (!owns() || state.busy || !prepared) return
    const command = prepared
    state.confirming = false
    state.busy = true
    state.error = ''
    try {
      const response = await api.accountCommand(command.action, command.userId, command.body)
      if (!owns()) return
      if (!response.data?.user_id || (command.userId && response.data.user_id !== command.userId))
        throw new Error('账号操作响应归属无效，请重试')
      state.message = '账号操作已完成'
      clearEditor()
      await load()
    } catch (error) {
      if (!owns()) return
      if (error.data?.error_code === 'username_conflict_or_invalid') {
        state.fieldErrors.username = '该用户名不可用，请使用其他用户名'
        state.error = '创建未完成，输入已保留'
        return
      }
      if (error.data?.error_code === 'last_admin_protected') {
        state.error = '需要保留至少一个启用的管理员，未执行修改'
        return
      }
      state.error =
        (error.httpStatus || error.code) === 409
          ? '账号版本或状态已变化。输入已保留，请关闭后刷新列表并重新编辑。'
          : error.message || '操作未确认，可使用原输入重试'
    } finally {
      if (owns()) state.busy = false
    }
  }
  function dispose() {
    active = false
    stopDraft()
    stopOwner()
    list.dispose()
    clearEditor()
    state.busy = false
    state.message = ''
  }
  return Object.assign(state, {
    load,
    open,
    close,
    clearEditor,
    prepare,
    confirm,
    dispose,
    setField,
    setConfirming,
    setDiscarding,
  })
}
