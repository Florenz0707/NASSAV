// Commands latch their membership CAS evidence until the outcome is known.
export function createLibraryCommands(
  api,
  { memberships, acceptOperation, changed, requestId = () => crypto.randomUUID() }
) {
  let epoch = 0,
    owner = ''
  const commands = new Map(),
    pending = new Map()
  const obsolete = () => Object.assign(new Error('登录上下文已变化'), { code: 'session_changed' })
  function reset(identity = '') {
    epoch++
    owner = identity
    commands.clear()
    pending.clear()
  }
  function execute(action, avid, { source = '', credential_mode = 'public' } = {}) {
    avid = String(avid || '')
      .trim()
      .toUpperCase()
    source = source.toLowerCase()
    if (!owner) return Promise.reject(obsolete())
    if (!avid || !['add', 'refresh', 'download', 'release'].includes(action))
      return Promise.reject(new Error('无效的资源操作'))
    if (
      action !== 'release' &&
      (!source || source === 'any' || !['public', 'personal'].includes(credential_mode))
    )
      return Promise.reject(new Error('请选择明确来源和凭证范围'))
    const key = JSON.stringify([action, avid, source, credential_mode])
    if (pending.has(key)) return pending.get(key)
    const current = epoch
    const operation = Promise.resolve().then(async () => {
      try {
        if (current !== epoch) throw obsolete()
        let command = commands.get(key)
        if (!command) {
          await memberships.load([avid], { force: true })
          if (current !== epoch) throw obsolete()
          if (memberships.errors.has(avid)) throw new Error(memberships.errors.get(avid))
          const entry = memberships.get(avid)
          if (!entry) throw new Error('无法确认本人的持有状态，请重试')
          if (
            action !== 'add' &&
            (!entry.is_in_my_library ||
              (action !== 'release' && entry.membership_state !== 'active'))
          )
            throw new Error('本人尚无可用持有关系，请重新加载列表')
          const body =
            action === 'release'
              ? { expected_version: entry.entry_version, request_id: requestId() }
              : {
                  action,
                  kind: action === 'download' ? 'download' : 'scrape',
                  source,
                  credential_mode,
                  request_id: requestId(),
                  ...(entry.is_in_my_library
                    ? { expected_entry_version: entry.entry_version }
                    : {}),
                }
          command = { entryId: entry.entry_id, body: action === 'add' ? { ...body, avid } : body }
          commands.set(key, command)
        }
        if (current !== epoch) throw obsolete()
        const response =
          action === 'add'
            ? await api.addEntry(command.body)
            : action === 'release'
              ? await api.releaseEntry(command.entryId, command.body)
              : await api.submitEntryOperation(command.entryId, command.body)
        if (current !== epoch) throw obsolete()
        if (action !== 'release') {
          const snapshot = response.data?.operation || response.data
          if (!snapshot?.operation_id || snapshot.avid !== avid || snapshot.action !== action)
            throw new Error('资源操作响应归属无效，请重试')
          acceptOperation(snapshot)
        }
        commands.delete(key)
        changed(avid, action)
        return response
      } catch (error) {
        if (current !== epoch) throw obsolete()
        // Definitive conflicts require a fresh explicit action, not an auto retry.
        if ((error.httpStatus || error.code) === 409) commands.delete(key)
        error.sharedLibrary = true
        throw error
      } finally {
        if (current === epoch && pending.get(key) === operation) pending.delete(key)
      }
    })
    pending.set(key, operation)
    return operation
  }
  async function batch(action, avids, options = {}) {
    const current = epoch,
      results = []
    const identities = [...new Set(avids.map((avid) => avid.trim().toUpperCase()))]
    if (identities.length > 100) throw new Error('单次最多操作100个资源')
    for (const avid of identities) {
      if (current !== epoch) throw obsolete()
      try {
        const response = await execute(action, avid, options)
        results.push({ avid, code: response.code || 200, data: response.data })
      } catch (error) {
        if (current !== epoch) throw obsolete()
        results.push({
          avid,
          code: error.httpStatus || error.code || 500,
          message: error.message || '操作未确认，请重试',
        })
      }
    }
    return results
  }
  return { reset, execute, batch }
}
