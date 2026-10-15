import test from 'node:test'
import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createSystemCredentials } from '../src/features/admin/lib/systemCredentials.js'

const row = (change = {}) => ({
  id: 'credential-1',
  source_name: 'jable',
  scope: 'system',
  kind: 'clearance',
  version: 2,
  state: 'active',
  ...change,
})
const create = (write, owner = () => 'admin-a', update = () => {}) =>
  createSystemCredentials(
    {
      list: async () => ({ data: [row()] }),
      sources: async () => ({ data: ['Jable'] }),
      write,
    },
    owner,
    update
  )
function fill(admin) {
  admin.setField('cookie', 'cf_clearance=private-test-token')
  admin.setField('userAgent', 'Browser-test/1.0')
}

test('system credential create permits classified cookies only and never sends account kind', async () => {
  const calls = []
  const admin = create(async (command) => {
    calls.push(command)
    return { data: row({ version: 1 }) }
  })
  await admin.load()
  admin.open()
  fill(admin)
  admin.setField('cookie', 'account_session=not-public')
  admin.prepare()
  assert.match(admin.errors.cookie, /不能包含账号/)
  admin.setField('cookie', 'cf_clearance=public-test')
  admin.prepare()
  await admin.confirm()
  assert.equal(calls[0].body.kind, 'clearance')
  assert.equal(calls[0].body.expected_version, 0)
  assert.equal(calls[0].source, 'jable')
  assert.equal(admin.draft.cookie, '')
  admin.dispose()
})

test('unknown system write outcome replays frozen endpoint/version/UUID, then clears secrets and invalidates source context', async () => {
  const calls = [],
    identities = []
  const admin = create(
    async (command) => {
      calls.push(structuredClone(command))
      if (calls.length === 1) throw new Error('network failure')
      return { data: row({ version: 3, source_cache_identity: 'next-context' }) }
    },
    () => 'admin',
    (identity) => identities.push(identity)
  )
  const original = row()
  admin.open(original)
  original.version = 9
  fill(admin)
  admin.prepare()
  await admin.confirm()
  assert.equal(admin.draft.cookie, 'cf_clearance=private-test-token')
  admin.prepare()
  await admin.confirm()
  assert.deepEqual(calls[0], calls[1])
  assert.equal(calls[1].body.expected_version, 2)
  assert.deepEqual(identities, ['next-context'])
  assert.equal(admin.draft.cookie, '')
  assert.equal(admin.editor, null)
  admin.dispose()
})

test('system conflict retains draft and target, edits create new command, revoke sends no secret fields', async () => {
  const calls = []
  const admin = create(async (command) => {
    calls.push(structuredClone(command))
    throw { httpStatus: 409 }
  })
  admin.open(row())
  fill(admin)
  admin.prepare()
  await admin.confirm()
  assert.match(admin.error, /重新编辑/)
  admin.setField('cookie', 'cf_clearance=changed')
  admin.prepare()
  await admin.confirm()
  assert.notEqual(calls[0].body.request_id, calls[1].body.request_id)
  assert.equal(calls[1].body.expected_version, 2)
  admin.clear()
  admin.open(row(), true)
  admin.prepare()
  await admin.confirm()
  assert.deepEqual(Object.keys(calls[2].body).sort(), ['expected_version', 'reason', 'request_id'])
  assert.equal(calls[2].revoke, true)
  admin.dispose()
})

test('owner change clears secrets synchronously and ignores late success and source list', async () => {
  const owner = ref('a')
  let resolve
  const identities = []
  const admin = create(
    () =>
      new Promise((yes) => {
        resolve = yes
      }),
    () => owner.value,
    (value) => identities.push(value)
  )
  admin.open(row())
  fill(admin)
  admin.prepare()
  const pending = admin.confirm()
  owner.value = 'b'
  assert.equal(admin.draft.cookie, '')
  assert.equal(admin.editor, null)
  resolve({ data: row({ source_cache_identity: 'old-context' }) })
  await pending
  assert.deepEqual(identities, [])
  assert.deepEqual(admin.list.rows, [])
  admin.dispose()
})

test('existing unconfigured source is still revocable; discard clears all secret drafts', async () => {
  const admin = create(async () => ({ data: row({ source_name: 'removed', state: 'revoked' }) }))
  await admin.load()
  admin.open(row({ source_name: 'removed' }), true)
  admin.prepare()
  assert.equal(admin.confirming, true)
  await admin.confirm()
  admin.open(row())
  fill(admin)
  admin.close()
  assert.equal(admin.discarding, true)
  admin.clear()
  assert.equal(admin.draft.userAgent, '')
  admin.dispose()
})
