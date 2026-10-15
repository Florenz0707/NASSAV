import test from 'node:test'
import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createWorkAdministration } from '../src/features/admin/lib/workAdministration.js'
const row = () => ({
  job_id: 'job-a',
  avid: 'TEST-001',
  version: 2,
  allowed_actions: ['pause', 'cancel'],
})
const create = (command, owner = () => 'a', list = async () => ({ data: [row()] })) =>
  createWorkAdministration({ command, list }, owner)

test('administrator controls respect allowed actions and freeze job version and command UUID on unknown outcome', async () => {
  const commands = []
  const admin = create(async (command) => {
    commands.push(structuredClone(command))
    if (commands.length === 1) throw new Error('network')
    return { data: { job_id: 'job-a' } }
  })
  const job = row()
  admin.open('resume', job)
  assert.equal(admin.editor, null)
  admin.open('pause', job)
  job.version = 9
  job.allowed_actions.length = 0
  admin.prepare()
  await admin.confirm()
  admin.prepare()
  await admin.confirm()
  assert.deepEqual(commands[0], commands[1])
  assert.equal(commands[0].body.expected_version, 2)
  assert.equal(admin.editor, null)
  assert.match(admin.message, /后台状态为准/)
  admin.dispose()
})

test('version conflict never silently adopts new task snapshot; changing reason creates new command', async () => {
  const commands = []
  const admin = create(async (command) => {
    commands.push(structuredClone(command))
    throw { httpStatus: 409, data: { ...row(), version: 9 } }
  })
  admin.open('cancel', row())
  admin.prepare()
  await admin.confirm()
  assert.equal(admin.editor.row.version, 2)
  assert.match(admin.error, /不会自动采用新版本/)
  admin.setReason('security')
  admin.prepare()
  await admin.confirm()
  assert.notEqual(commands[0].body.request_id, commands[1].body.request_id)
  assert.equal(commands[1].body.expected_version, 2)
  admin.dispose()
})

test('owner change ignores delayed control and clears stale administrator state', async () => {
  const owner = ref('a')
  let finish,
    reloads = 0
  const admin = create(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
    () => owner.value,
    async () => {
      reloads++
      return { data: [] }
    }
  )
  admin.open('pause', row())
  admin.prepare()
  const pending = admin.confirm()
  owner.value = 'b'
  finish({ data: { job_id: 'job-a' } })
  await pending
  assert.equal(admin.editor, null)
  assert.equal(admin.message, '')
  assert.equal(reloads, 0)
  admin.dispose()
})

test('busy spans the successful command and list reload, foreign responses retain retry evidence', async () => {
  let finish
  const admin = create(
    async () => ({ data: { job_id: 'job-a' } }),
    undefined,
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  admin.open('pause', row())
  admin.prepare()
  const pending = admin.confirm()
  await Promise.resolve()
  assert.equal(admin.busy, true)
  admin.open('cancel', row())
  assert.equal(admin.editor, null)
  finish({ data: [row()] })
  await pending
  assert.equal(admin.busy, false)
  admin.dispose()
  const foreign = create(async () => ({ data: { job_id: 'another-job' } }))
  foreign.open('pause', row())
  foreign.prepare()
  await foreign.confirm()
  assert.match(foreign.error, /归属无效/)
  assert.equal(foreign.editor.row.job_id, 'job-a')
  foreign.dispose()
})

test('work HTTP adapter unwraps paginated jobs and routes cleanup retry to the existing endpoint', async () => {
  const { workAdminApi } = await import('../src/api/admin.js')
  const { default: client } = await import('../src/api/client.js')
  const original = client.defaults.adapter
  const calls = []
  client.defaults.adapter = async (config) => {
    calls.push(config)
    return {
      status: 200,
      config,
      headers: {},
      data: {
        code: 200,
        message: 'success',
        data: config.method === 'get' ? { jobs: [row()], pagination: { total: 1 } } : row(),
      },
    }
  }
  try {
    const response = await workAdminApi.list({ page: 1, page_size: 20 })
    assert.equal(response.data[0].job_id, 'job-a')
    assert.equal(response.pagination.total, 1)
    await workAdminApi.command({
      id: 'job-a',
      action: 'cleanup_retry',
      body: { expected_version: 2 },
    })
    assert.equal(calls[1].url, '/tasks/jobs/job-a/cleanup/retry')
    await assert.rejects(workAdminApi.command({ id: 'job-a', action: 'delete', body: {} }))
    assert.equal(calls.length, 2)
  } finally {
    client.defaults.adapter = original
  }
})
