import test from 'node:test'
import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createResourceAdministration } from '../src/features/admin/lib/resourceAdministration.js'
const pool = (change = {}) => ({
  pool_id: 'pool-a',
  avid: 'TEST-001',
  pool_version: 2,
  generation: 1,
  is_available: true,
  retained: false,
  ...change,
})
const snapshot = (change = {}) => ({
  pool_id: 'pool-a',
  pool_version: 2,
  pool_generation: 1,
  version_id: null,
  eligible: true,
  blockers: [],
  ...change,
})
const create = (api = {}, gc = () => true, owner = () => 'a', applied = () => {}) =>
  createResourceAdministration(
    {
      preview: async () => ({ data: snapshot() }),
      command: async () => ({ data: { pool_id: 'pool-a' } }),
      ...api,
    },
    owner,
    gc,
    applied
  )

test('disabled GC keeps preview read-only and permits retention, never enqueue/retry', async () => {
  const commands = []
  const admin = create(
    {
      command: async (command) => {
        commands.push(command)
        return { data: { pool_id: 'pool-a' } }
      },
    },
    () => false
  )
  await admin.open('preview', pool())
  assert.equal(admin.preview.eligible, true)
  admin.prepare()
  await admin.confirm()
  assert.equal(commands.length, 0)
  assert.match(admin.error, /尚未开启/)
  admin.open('retention', pool())
  admin.prepare()
  await admin.confirm()
  assert.equal(commands[0].body.retained, true)
  assert.equal(commands[0].body.expected_version, 2)
  assert.equal(admin.editor, null)
  admin.dispose()
})

test('pool snapshot CAS and same UUID survive lost availability response', async () => {
  const commands = []
  let refreshed = 0
  const admin = create(
    {
      command: async (command) => {
        commands.push(structuredClone(command))
        if (commands.length === 1) throw new Error('network failure')
        return { data: { pool_id: 'pool-a', available: false, version: 3 } }
      },
    },
    undefined,
    undefined,
    () => {
      refreshed++
    }
  )
  const row = pool()
  admin.open('availability', row)
  row.pool_version = 9
  admin.prepare()
  await admin.confirm()
  assert.equal(admin.editor.row.pool_version, 2)
  admin.prepare()
  await admin.confirm()
  assert.deepEqual(commands[0], commands[1])
  assert.equal(commands[0].body.available, false)
  assert.equal(refreshed, 1)
  admin.dispose()
})

test('new reasons create a new command, conflicts preserve fixed versions and show blockers', async () => {
  const commands = []
  const admin = create({
    command: async (command) => {
      commands.push(structuredClone(command))
      throw { httpStatus: 409, data: { blockers: ['read_leases'] } }
    },
  })
  admin.open('retention', pool())
  admin.prepare()
  await admin.confirm()
  assert.deepEqual(admin.blockers, ['read_leases'])
  admin.setReason('security')
  admin.prepare()
  await admin.confirm()
  assert.notEqual(commands[0].body.request_id, commands[1].body.request_id)
  assert.equal(commands[1].body.expected_version, 2)
  assert.match(admin.error, /刷新确认/)
  admin.dispose()
})

test('enqueue requires matching preview and preserves exact version UUID in request', async () => {
  const version = '550e8400-e29b-41d4-a716-446655440000'
  const commands = []
  const admin = create({
    preview: async (id, versionId) => ({ data: snapshot({ version_id: versionId || null }) }),
    command: async (command) => {
      commands.push(command)
      return { data: { pool_id: 'pool-a', job_id: 'gc-a' } }
    },
  })
  await admin.open('preview', pool())
  admin.setVersion('wrong')
  await admin.loadPreview()
  admin.prepare()
  assert.equal(admin.confirming, false)
  admin.setVersion(version.toUpperCase())
  await admin.loadPreview()
  admin.prepare()
  await admin.confirm()
  assert.equal(commands[0].action, 'enqueue')
  assert.equal(commands[0].body.version_id, version)
  assert.match(admin.message, /结果以回收记录为准/)
  admin.dispose()
})

test('newer pool versions and foreign previews cannot authorize enqueue', async () => {
  for (const result of [
    snapshot({ pool_version: 3 }),
    snapshot({ pool_id: 'another-pool' }),
    snapshot({ pool_generation: 2 }),
  ]) {
    const admin = create({ preview: async () => ({ data: result }) })
    await admin.open('preview', pool())
    assert.equal(admin.preview, null)
    assert.ok(admin.error)
    admin.prepare()
    assert.equal(admin.confirming, false)
    admin.dispose()
  }
})

test('retry uses job revision rather than pool version and rechecks feature gate at confirmation', async () => {
  let enabled = true
  const commands = []
  const admin = create(
    {
      command: async (command) => {
        commands.push(command)
        return { data: { pool_id: 'pool-a', job_id: 'gc-a' } }
      },
    },
    () => enabled
  )
  admin.open('retry', { pool_id: 'pool-a', job_id: 'gc-a', revision: 7 })
  admin.prepare()
  enabled = false
  await admin.confirm()
  assert.equal(commands.length, 0)
  enabled = true
  await admin.confirm()
  assert.equal(commands[0].body.expected_version, 7)
  admin.dispose()
})

test('changed owner or disposed preview cannot publish old result or refresh new session', async () => {
  const owner = ref('a')
  let resolve,
    refreshed = 0
  const admin = create(
    {
      preview: () =>
        new Promise((yes) => {
          resolve = yes
        }),
    },
    undefined,
    () => owner.value,
    () => {
      refreshed++
    }
  )
  const pending = admin.open('preview', pool())
  owner.value = 'b'
  assert.equal(admin.editor, null)
  resolve({ data: snapshot() })
  await pending
  assert.equal(admin.preview, null)
  assert.equal(admin.previewLoading, false)
  assert.equal(refreshed, 0)
  admin.dispose()
})

test('successful command holds its busy guard until list invalidation finishes', async () => {
  let finish
  const admin = create(
    {},
    undefined,
    undefined,
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  admin.open('retention', pool())
  admin.prepare()
  const pending = admin.confirm()
  await Promise.resolve()
  assert.equal(admin.editor, null)
  assert.equal(admin.busy, true)
  admin.open('availability', pool())
  assert.equal(admin.editor, null)
  finish()
  await pending
  assert.equal(admin.busy, false)
  admin.dispose()
})

test('malformed eligible flags and inconsistent blockers never authorize a deletion request', async () => {
  for (const result of [
    snapshot({ eligible: 'yes' }),
    snapshot({ blockers: ['memberships'] }),
    snapshot({ blockers: [null] }),
  ]) {
    const admin = create({ preview: async () => ({ data: result }) })
    await admin.open('preview', pool())
    assert.equal(admin.preview, null)
    admin.prepare()
    assert.equal(admin.confirming, false)
    admin.dispose()
  }
})
