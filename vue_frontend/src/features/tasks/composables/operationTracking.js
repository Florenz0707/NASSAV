import { createRequestId } from '../../../shared/lib/requestId.js'
import { computed, ref } from 'vue'

const ended = new Set(['succeeded', 'failed', 'cancelled'])

// Raw user operations stay distinct from shared jobs and executor attempts.
export function createOperationTracking(
  api,
  {
    changed = () => {},
    requestId = () => createRequestId(),
    storage = () => globalThis.localStorage,
  } = {}
) {
  const operations = ref(new Map()),
    hidden = ref(new Set()),
    busy = ref(new Set())
  const loading = ref(false),
    error = ref(''),
    listError = ref(''),
    total = ref(0),
    hasMore = ref(false)
  const ordering = ref('-created_at')
  const visible = computed(() =>
    [...operations.value.values()].filter((item) => !hidden.value.has(item.operation_id))
  )
  let epoch = 0,
    listRevision = 0,
    page = 0,
    owner = '',
    timer = null
  const pending = new Map(),
    commands = new Map(),
    submittedIds = new Set()
  function apply(item, { submitted = false } = {}) {
    if (!item?.operation_id || !Number.isInteger(item.version) || item.version < 1) return null
    const old = operations.value.get(item.operation_id)
    const announce = submitted && !submittedIds.has(item.operation_id)
    if (announce) submittedIds.add(item.operation_id)
    if (old && old.version >= item.version) {
      if (announce) changed(old, old, { submitted: true })
      return old
    }
    operations.value = new Map(operations.value).set(item.operation_id, item)
    changed(item, old, { submitted: announce })
    return item
  }
  async function load(more = false) {
    if (!owner || loading.value) return
    const current = epoch,
      revision = listRevision,
      target = more ? page + 1 : 1
    loading.value = true
    try {
      const response = await api.listOperations({
        page: target,
        page_size: 20,
        ordering: ordering.value,
      })
      if (current !== epoch || revision !== listRevision) return
      if (!Array.isArray(response.data) || !Number.isInteger(response.pagination?.total))
        throw new Error('本人请求列表格式无效')
      response.data.forEach((item) => apply(item))
      page = more ? target : Math.max(page, target)
      total.value = response.pagination.total
      hasMore.value = page < response.pagination.pages
      listError.value = ''
    } catch (reason) {
      if (current === epoch && revision === listRevision)
        listError.value = reason.message || '无法读取本人请求'
    } finally {
      if (current === epoch && revision === listRevision) loading.value = false
    }
  }
  async function refresh(id, quiet = false) {
    if (!owner) return
    if (pending.has(id)) return pending.get(id)
    const current = epoch
    const operation = Promise.resolve().then(async () => {
      try {
        if (current !== epoch) return
        const response = await api.getOperation(id)
        if (current === epoch && response.data?.operation_id === id) return apply(response.data)
      } catch (reason) {
        if (current === epoch && !quiet) listError.value = reason.message || '请求状态更新失败'
      } finally {
        if (current === epoch && pending.get(id) === operation) pending.delete(id)
      }
    })
    pending.set(id, operation)
    return operation
  }
  async function poll(all = false) {
    return Promise.allSettled(
      visible.value
        .filter((item) => all || !ended.has(item.state))
        .map((item) => refresh(item.operation_id))
    )
  }
  function hint(event) {
    if (!owner || !event?.operation_id || hidden.value.has(event.operation_id)) return
    if (event.version <= (operations.value.get(event.operation_id)?.version || 0)) return
    const current = epoch
    refresh(event.operation_id, true).then(() => {
      if (
        current === epoch &&
        event.version > (operations.value.get(event.operation_id)?.version || 0)
      )
        refresh(event.operation_id, true)
    })
  }
  async function cancel(ids) {
    if (!owner) return []
    const current = epoch
    const items = [...new Set(ids)]
      .filter((id) => !busy.value.has(id))
      .map((id) => operations.value.get(id))
      .filter((item) => item?.allowed_actions?.includes('cancel'))
    busy.value = new Set([...busy.value, ...items.map((item) => item.operation_id)])
    error.value = ''
    const results = []
    for (const item of items) {
      if (current !== epoch) break
      const id = item.operation_id,
        key = `${id}:${item.version}`
      const commandId = commands.get(key) || requestId()
      commands.set(key, commandId)
      try {
        const response = await api.cancelOperation(id, {
          expected_version: item.version,
          request_id: commandId,
        })
        if (current !== epoch) break
        if (response.data?.operation_id !== id) throw new Error('请求响应归属无效')
        apply(response.data)
        commands.delete(key)
        results.push({ operation_id: id, ok: true })
      } catch (reason) {
        if (current !== epoch) break
        error.value = [error.value, `${item.avid}：${reason.message || '撤销未确认，请重试'}`]
          .filter(Boolean)
          .join('；')
        results.push({ operation_id: id, ok: false })
        if ((reason.httpStatus || reason.code) === 409) await refresh(id, true)
      } finally {
        if (current === epoch) busy.value = new Set([...busy.value].filter((value) => value !== id))
      }
    }
    return results
  }
  function hide(ids) {
    hidden.value = new Set([...hidden.value, ...ids])
    try {
      if (owner)
        storage()?.setItem(
          `nassav:hidden-operations:v1:${owner}`,
          JSON.stringify([...hidden.value])
        )
    } catch {
      /* Optional local display preference. */
    }
  }
  function reset(identity = '') {
    epoch++
    listRevision++
    owner = identity
    if (timer) clearInterval(timer)
    timer = null
    page = 0
    ordering.value = '-created_at'
    operations.value = new Map()
    hidden.value = new Set()
    busy.value = new Set()
    loading.value = false
    error.value = listError.value = ''
    total.value = 0
    hasMore.value = false
    pending.clear()
    commands.clear()
    submittedIds.clear()
  }
  function start(identity) {
    reset(identity)
    try {
      const saved = JSON.parse(storage()?.getItem(`nassav:hidden-operations:v1:${owner}`) || '[]')
      if (Array.isArray(saved)) hidden.value = new Set(saved.filter((id) => typeof id === 'string'))
    } catch {
      /* Invalid local display preferences do not affect server tracking. */
    }
    if (!owner) return
    load()
    let ticks = 0
    timer = setInterval(() => {
      ticks++
      poll(ticks % 15 === 0)
      if (ticks % 15 === 0) load()
    }, 2000)
  }
  function setOrdering(value) {
    if (!['-created_at', '-updated_at'].includes(value) || ordering.value === value) return
    ordering.value = value
    listRevision++
    page = 0
    operations.value = new Map()
    loading.value = false
    hasMore.value = false
    return load()
  }
  return {
    operations,
    visible,
    busy,
    loading,
    error,
    listError,
    total,
    hasMore,
    ordering,
    apply,
    load,
    refresh,
    poll,
    hint,
    cancel,
    hide,
    reset,
    start,
    setOrdering,
  }
}
