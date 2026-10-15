import test from 'node:test'
import { ref } from 'vue'
import assert from 'node:assert/strict'
import { createAccountAdministration } from '../src/features/admin/lib/accountAdministration.js'
import { createAdminRead } from '../src/features/admin/lib/adminRead.js'

const account = (changes = {}) => ({
  user_id: 7,
  username: 'member',
  role: 'user',
  is_active: true,
  version: 2,
  storage_quota_bytes: null,
  max_active_operations: 2,
  ...changes,
})
const response = (row = account()) => ({ data: row })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const create = (command, owner = () => 'admin-a') =>
  createAccountAdministration(
    {
      listUsers: async () => ({ data: [account()], pagination: { total: 1 } }),
      accountCommand: command,
    },
    owner,
    { requestId: () => crypto.randomUUID() }
  )

test('quota-only edits do not send role/active fields or cause an implicit role mutation', async () => {
  const bodies = []
  const admin = create(async (action, id, body) => {
    bodies.push(body)
    return response(account({ version: 3, max_active_operations: 5 }))
  })
  const rendered = account()
  admin.open('update', rendered)
  rendered.version = 9
  admin.draft.operations = '5'
  admin.prepare()
  assert.equal(admin.confirming, true)
  await admin.confirm()
  assert.equal(bodies[0].max_active_operations, 5)
  assert.equal(bodies[0].expected_version, 2)
  assert.equal(Object.hasOwn(bodies[0], 'role'), false)
  assert.equal(Object.hasOwn(bodies[0], 'is_active'), false)
  assert.equal(Object.hasOwn(bodies[0], 'storage_quota_bytes'), false)
  admin.dispose()
})

test('unknown outcome retries the same command UUID and frozen version; password is cleared after success', async () => {
  const calls = []
  const admin = create(async (action, id, body) => {
    calls.push({ ...body })
    if (calls.length === 1) throw new Error('outcome unknown')
    return response(account({ version: 3 }))
  })
  admin.open('reset_password', account())
  admin.draft.password = 'Disposable-test-secret-123!'
  admin.prepare()
  await admin.confirm()
  assert.equal(admin.editor.action, 'reset_password')
  assert.equal(admin.draft.password, 'Disposable-test-secret-123!')
  admin.prepare()
  await admin.confirm()
  assert.equal(calls.length, 2)
  assert.deepEqual(calls[0], calls[1])
  assert.equal(admin.draft.password, '')
  assert.equal(admin.editor, null)
  admin.dispose()
})

test('editing a failed command creates a new UUID and server conflict never adopts a new account version', async () => {
  const calls = []
  const admin = create(async (action, id, body) => {
    calls.push({ ...body })
    throw { code: 409, message: 'conflict', data: { error_code: 'account_version_conflict' } }
  })
  admin.open('update', account())
  admin.draft.operations = '4'
  admin.prepare()
  await admin.confirm()
  assert.equal(admin.draft.operations, '4')
  admin.draft.operations = '6'
  admin.prepare()
  await admin.confirm()
  assert.notEqual(calls[0].request_id, calls[1].request_id)
  assert.equal(calls[1].expected_version, 2)
  assert.match(admin.error, /重新编辑/)
  admin.dispose()
})

test('validation rejects booleans/unsafe quotas, and closing unsaved input requires discard', async () => {
  const calls = []
  const admin = create(async (action, id, body) => {
    calls.push(body)
    return response()
  })
  admin.open('update', account())
  admin.draft.operations = true
  admin.prepare()
  assert.ok(admin.fieldErrors.operations)
  admin.draft.operations = '4'
  admin.draft.unlimited = false
  admin.draft.quota = '99999999999999999999'
  admin.prepare()
  assert.ok(admin.fieldErrors.quota)
  admin.draft.quota = '1.5'
  admin.prepare()
  assert.equal(admin.confirming, true)
  admin.close()
  assert.equal(admin.discarding, true)
  admin.clearEditor()
  assert.equal(admin.editor, null)
  assert.equal(calls.length, 0)
  admin.dispose()
})

test('old administrator responses cannot publish results, reload accounts or keep secrets after disposal', async () => {
  let owner = 'admin-a'
  const pending = deferred()
  const admin = create(
    () => pending.promise,
    () => owner
  )
  admin.open('create')
  admin.draft.username = 'new-member'
  admin.draft.password = 'Disposable-test-secret-123!'
  admin.prepare()
  const old = admin.confirm()
  owner = 'admin-b'
  admin.dispose()
  pending.resolve(response())
  await old
  assert.equal(admin.message, '')
  assert.equal(admin.draft.password, '')
  assert.equal(admin.list.rows.length, 0)
})

test('admin list discards stale failures and old owner results', async () => {
  const requests = []
  let owner = 'a'
  const list = createAdminRead(
    () => {
      const pending = deferred()
      requests.push(pending)
      return pending.promise
    },
    () => owner
  )
  const old = list.load(),
    current = list.load()
  requests[0].reject(new Error('old error'))
  await old
  assert.equal(list.loading, true)
  assert.equal(list.error, '')
  requests[1].resolve({ data: [account()] })
  await current
  const late = list.load()
  owner = 'b'
  list.dispose()
  requests[2].resolve({ data: [account({ username: 'old private user' })] })
  await late
  assert.deepEqual(list.rows, [])
})

test('reactive administrator identity change clears form secrets synchronously', () => {
  const owner = ref('a')
  const admin = create(
    async () => response(),
    () => owner.value
  )
  admin.open('create')
  admin.draft.password = 'Disposable-secret-123!'
  owner.value = 'b'
  assert.equal(admin.draft.password, '')
  assert.equal(admin.editor, null)
  assert.deepEqual(admin.list.rows, [])
  admin.dispose()
})

test('numeric formatting alone does not mutate quota policy or revoke role sessions', () => {
  const admin = create(async () => response())
  admin.open('update', account({ storage_quota_bytes: 1610612736 }))
  admin.setField('quota', '1.50')
  admin.setField('operations', '02')
  admin.prepare()
  assert.equal(admin.confirming, false)
  assert.equal(admin.error, '尚未修改账号配置')
  admin.dispose()
})
