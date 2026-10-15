import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { sourceApi } from '../../../api/index.js'
import { personalCredentialApi } from '../../../api/credentials.js'
import { useSessionStore } from '../../auth/stores/session.js'
import { createRequestGuard } from '../../../shared/lib/requestGuard.js'

export function usePersonalCredentials() {
  const session = useSessionStore()
  const sources = ref([]),
    rows = ref([]),
    selected = ref('')
  const cookie = ref(''),
    userAgent = ref(''),
    kind = ref('account')
  const cookieError = ref(''),
    userAgentError = ref('')
  watch(
    cookie,
    () => {
      cookieError.value = ''
    },
    { flush: 'sync' }
  )
  watch(
    userAgent,
    () => {
      userAgentError.value = ''
    },
    { flush: 'sync' }
  )
  const loading = ref(false),
    busy = ref(false),
    action = ref(''),
    error = ref(''),
    message = ref('')
  const guard = createRequestGuard()
  const owner = session.identity
  let disposed = false,
    editVersion = 0
  const current = () =>
    !disposed && session.status === 'authenticated' && session.identity === owner
  const credential = computed(() =>
    rows.value.find((row) => row.source_name.toLowerCase() === selected.value)
  )
  watch(
    selected,
    () => {
      editVersion++
      cookie.value = userAgent.value = error.value = message.value = ''
      cookieError.value = userAgentError.value = ''
      kind.value = credential.value?.kind || 'account'
    },
    { flush: 'sync' }
  )
  async function load() {
    const ticket = guard.begin()
    loading.value = true
    error.value = ''
    try {
      const [available, credentials] = await Promise.all([
        sourceApi.getList(),
        personalCredentialApi.list(),
      ])
      if (!current() || !guard.current(ticket)) return
      sources.value = (available.data || []).map((name) => ({
        label: name,
        value: name.toLowerCase(),
      }))
      rows.value = credentials.data || []
      if (!sources.value.some((item) => item.value === selected.value))
        selected.value = sources.value[0]?.value || ''
    } catch (failure) {
      if (current() && guard.current(ticket)) error.value = failure.message || '无法读取个人凭证'
    } finally {
      if (current() && guard.current(ticket)) loading.value = false
    }
  }
  async function save(revoke = false) {
    if (!current() || busy.value || loading.value || !selected.value) return
    cookieError.value = userAgentError.value = ''
    if (!revoke && !cookie.value.trim()) {
      cookieError.value = '请填写 Cookie 字符串'
      return
    }
    if (!revoke && !userAgent.value.trim()) {
      userAgentError.value = '请填写与 Cookie 配套的 User-Agent'
      return
    }
    const row = credential.value
    if (revoke && (!row || row.state === 'revoked')) return
    const editor = editVersion
    const target = selected.value
    busy.value = true
    action.value = revoke ? 'revoke' : 'save'
    error.value = message.value = ''
    try {
      const payload = {
        expected_version: row?.version || 0,
        cookie: cookie.value.trim(),
        user_agent: userAgent.value.trim(),
        kind: kind.value,
      }
      const response = revoke
        ? await personalCredentialApi.revoke(row.id, row.version)
        : row
          ? await personalCredentialApi.update(row.id, payload)
          : await personalCredentialApi.create({ source_name: target, ...payload })
      if (!current() || editor !== editVersion) return
      rows.value = [
        ...rows.value.filter((item) => item.source_name.toLowerCase() !== target),
        response.data,
      ]
      cookie.value = userAgent.value = ''
      session.updateSourceIdentity(response.data.source_cache_identity)
      if (current() && editor === editVersion)
        message.value = revoke ? '个人凭证已撤销' : '个人凭证已保存，内容不会回显'
    } catch (failure) {
      if (current() && editor === editVersion)
        error.value =
          failure.httpStatus === 409
            ? '凭证版本已变化，请重新加载并确认后保存'
            : failure.message || '操作未确认，请重新加载核对'
    } finally {
      if (current() && editor === editVersion) {
        busy.value = false
        action.value = ''
      }
    }
  }
  onBeforeUnmount(() => {
    disposed = true
    guard.invalidate()
    editVersion++
    cookie.value = userAgent.value = ''
  })
  return {
    sources,
    selected,
    credential,
    cookie,
    cookieError,
    userAgent,
    userAgentError,
    kind,
    loading,
    busy,
    action,
    error,
    message,
    load,
    save,
  }
}
