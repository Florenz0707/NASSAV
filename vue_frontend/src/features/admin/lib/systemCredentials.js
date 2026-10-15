import { reactive, watch } from 'vue'
import { createAdminRead } from './adminRead.js'

const reasons = new Set(['maintenance', 'security', 'user_request'])
const cookieNames = new Set(['cf_clearance', '__cf_bm', '__cflb'])
const empty = () => ({ source: '', cookie: '', userAgent: '', reason: 'maintenance' })

// System writes have audited, durable command receipts; personal writes do not.
export function createSystemCredentials(
  api,
  currentOwner,
  updateIdentity,
  { requestId = () => crypto.randomUUID() } = {}
) {
  const owner = currentOwner()
  const list = createAdminRead(api.list, currentOwner)
  const state = reactive({
    list,
    sources: [],
    editor: null,
    draft: empty(),
    errors: {},
    error: '',
    message: '',
    busy: false,
    dirty: false,
    confirming: false,
    discarding: false,
  })
  let active = true,
    prepared = null,
    nonce = null,
    loadVersion = 0
  const owns = () => active && Boolean(owner) && currentOwner() === owner
  const stopDraft = watch(
    () => state.draft,
    () => {
      if (state.editor && !state.busy) {
        state.dirty = true
        state.errors = {}
        state.error = ''
        prepared = nonce = null
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
  async function load() {
    const ticket = ++loadVersion
    state.error = ''
    await list.load()
    if (!owns() || ticket !== loadVersion) return
    // Configured sources are for creation only; existing rows remain revocable.
    try {
      const response = await api.sources()
      if (owns() && ticket === loadVersion)
        state.sources = (response.data || []).map((name) => ({
          value: name.toLowerCase(),
          label: name,
        }))
    } catch (error) {
      if (owns() && ticket === loadVersion)
        state.error = error.message || '无法读取来源列表，仍可管理现有凭证'
    }
  }
  function open(row = null, revoke = false) {
    if (!owns() || state.busy) return
    state.editor = null
    state.draft = {
      ...empty(),
      source: row?.source_name || state.sources[0]?.value || '',
      reason: revoke ? 'security' : 'maintenance',
    }
    state.editor = { row: row ? { ...row } : null, revoke }
    state.dirty = false
    state.error = ''
    state.errors = {}
    state.confirming = state.discarding = false
    prepared = nonce = null
  }
  function setField(key, value) {
    if (owns() && !state.busy && Object.hasOwn(state.draft, key)) state.draft[key] = value
  }
  function clear() {
    state.editor = null
    state.draft = empty()
    state.dirty = state.confirming = state.discarding = false
    state.error = ''
    state.errors = {}
    prepared = nonce = null
  }
  function close() {
    if (state.busy) return
    if (state.dirty) state.discarding = true
    else clear()
  }
  function prepare() {
    if (!owns() || !state.editor || state.busy) return
    const { row, revoke } = state.editor,
      draft = state.draft,
      errors = {}
    if (!draft.source || (!row && !state.sources.some((item) => item.value === draft.source)))
      errors.source = '请选择可用来源'
    if (!reasons.has(draft.reason)) errors.reason = '请选择操作原因'
    const body = { expected_version: row?.version || 0, reason: draft.reason }
    if (!revoke) {
      const cookie = draft.cookie.trim(),
        agent = draft.userAgent.trim()
      const parts = cookie.split(';').map((part) => part.trim())
      const names = parts.map((part) => part.split('=')[0])
      if (
        !cookie ||
        cookie.length > 32768 ||
        names.some((name) => !cookieNames.has(name)) ||
        new Set(names).size !== names.length ||
        parts.some((part) => !/^[^=]+=.+$/.test(part))
      )
        errors.cookie = '仅接受 cf_clearance、__cf_bm、__cflb，不能包含账号 Cookie'
      if (!agent || agent.length > 2048 || /[^\x20-\x7e]/.test(agent))
        errors.userAgent = '请填写有效且与 Cookie 配套的 User-Agent'
      Object.assign(body, { cookie, user_agent: agent, kind: 'clearance' })
    }
    state.errors = errors
    if (Object.keys(errors).length) return
    nonce ||= requestId()
    prepared = {
      id: row?.id || null,
      source: draft.source,
      revoke,
      body: { ...body, request_id: nonce },
    }
    state.confirming = true
  }
  async function confirm() {
    if (!owns() || state.busy || !prepared) return
    const command = prepared
    state.confirming = false
    state.busy = true
    state.error = ''
    try {
      const response = await api.write(command)
      if (!owns()) return
      const row = response.data
      if (
        row?.scope !== 'system' ||
        row.source_name !== command.source ||
        (command.id && row.id !== command.id)
      )
        throw new Error('凭证响应归属无效，请使用原输入重试')
      clear()
      state.message = command.revoke ? '系统凭证已撤销' : '系统访问验证凭证已保存，内容不会回显'
      updateIdentity(row.source_cache_identity)
      if (owns()) await list.load()
    } catch (error) {
      if (owns())
        state.error =
          (error.httpStatus || error.code) === 409
            ? '凭证版本已变化，输入已保留。请关闭后刷新列表并重新编辑。'
            : error.message || '操作未确认，可使用原输入重试'
    } finally {
      if (owns()) state.busy = false
    }
  }
  function dispose() {
    active = false
    loadVersion++
    stopDraft()
    stopOwner()
    list.dispose()
    clear()
    state.sources = []
    state.busy = false
    state.message = ''
  }
  return Object.assign(state, {
    load,
    open,
    setField,
    clear,
    close,
    prepare,
    confirm,
    dispose,
    setConfirming: (value) => {
      state.confirming = Boolean(value)
    },
    setDiscarding: (value) => {
      state.discarding = Boolean(value)
    },
  })
}
