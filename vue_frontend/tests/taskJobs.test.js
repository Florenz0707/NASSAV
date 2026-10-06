import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { taskApi } from '../src/api/index.js'
import { useTaskJobsStore } from '../src/stores/taskJobs.js'
const job = (changes = {}) => ({
  job_id: 'stable',
  task_id: 'attempt-1',
  job_type: 'scrape',
  avid: 'AV-1',
  state: 'running',
  version: 2,
  allowed_actions: ['pause', 'cancel'],
  ...changes,
})
const response = (data) => ({ data })

test('stable identity and version guard reject late attempt snapshots; hide survives refresh', async () => {
  setActivePinia(createPinia())
  const store = useTaskJobsStore()
  store.apply(job())
  store.apply(job({ version: 4, state: 'paused', allowed_actions: ['resume', 'cancel'] }))
  store.apply(job({ version: 3, state: 'running' }))
  assert.equal(store.visible[0].state, 'paused')
  store.apply(job({ version: 5, task_id: 'attempt-2', state: 'queued' }))
  assert.equal(store.jobs.size, 1)
  store.hide(['stable'])
  store.apply(job({ version: 6 }))
  assert.equal(store.visible.length, 0)
  store.reset()
})

test('batch controls preserve partial conflict snapshots and no optimistic stopped state', async () => {
  setActivePinia(createPinia())
  const store = useTaskJobsStore()
  store.apply(job())
  store.apply(job({ job_id: 'second', avid: 'AV-2' }))
  let resolve
  const original = taskApi.controlJobs
  taskApi.controlJobs = () =>
    new Promise((done) => {
      resolve = () =>
        done(
          response({
            results: [
              { job_id: 'stable', code: 202, job: job({ version: 3, state: 'pausing' }) },
              {
                job_id: 'second',
                code: 409,
                message: '版本冲突',
                job: job({ job_id: 'second', avid: 'AV-2', version: 4, state: 'succeeded' }),
              },
            ],
          })
        )
    })
  try {
    const operation = store.control('pause', ['stable', 'second'])
    await new Promise((done) => setTimeout(done, 0))
    assert.equal(store.jobs.get('stable').state, 'running')
    assert.ok(store.busy.has('stable'))
    resolve()
    await operation
    assert.equal(store.jobs.get('stable').state, 'pausing')
    assert.equal(store.jobs.get('second').state, 'succeeded')
    assert.match(store.error, /AV-2.*版本冲突/)
    assert.equal(store.busy.size, 0)
  } finally {
    taskApi.controlJobs = original
    store.reset()
  }
})

test('logout invalidates late commands and late list loading/error state', async () => {
  setActivePinia(createPinia())
  const store = useTaskJobsStore(),
    original = taskApi.controlJobs,
    originalList = taskApi.listJobs
  const replies = []
  taskApi.controlJobs = () =>
    new Promise((resolve) => replies.push((data) => resolve(response(data))))
  taskApi.listJobs = taskApi.controlJobs
  try {
    store.apply(job())
    const command = store.control('cancel', ['stable']),
      list = store.load()
    await new Promise((done) => setTimeout(done, 0))
    store.reset()
    replies[0]({
      results: [{ job_id: 'stable', code: 202, job: job({ version: 3, state: 'cancelling' }) }],
    })
    replies[1]({ jobs: [job()], pagination: { total: 1, has_more: false } })
    await Promise.all([command, list])
    assert.equal(store.jobs.size, 0)
    assert.equal(store.loading, false)
    assert.equal(store.error, '')
    assert.equal(store.busy.size, 0)
  } finally {
    taskApi.controlJobs = original
    taskApi.listJobs = originalList
    store.reset()
  }
})

test('uncertain network commands retry with the same request UUID', async () => {
  setActivePinia(createPinia())
  const store = useTaskJobsStore(),
    original = taskApi.controlJobs,
    ids = []
  store.apply(job())
  taskApi.controlJobs = async (payload) => {
    ids.push(payload.request_id)
    if (ids.length === 1) throw new Error('lost response')
    return response({
      results: [{ job_id: 'stable', code: 202, job: job({ version: 3, state: 'pausing' }) }],
    })
  }
  try {
    await store.control('pause', ['stable'])
    await store.control('pause', ['stable'])
    assert.equal(ids.length, 2)
    assert.equal(ids[0], ids[1])
  } finally {
    taskApi.controlJobs = original
    store.reset()
  }
})
