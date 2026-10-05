import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { mergeScrapeJob } from '../src/stores/scrapeJobState.js'

const calls = []
let remoteState = 'queued'
let remoteVersion = 1
let remoteStage = null
let submitTaskId = 'job-1'
let holdNextSnapshot = false
let releaseSnapshot = null
axios.defaults.adapter = async (config) => {
  calls.push({
    url: config.url,
    method: config.method,
    token: config.headers?.['X-Resource-Job-Token'],
  })
  if (config.url === '/resource/jobs' && config.method === 'post') {
    return response(config, 202, {
      task_id: submitTaskId,
      status_token: 'signed-token',
      job: {
        task_id: submitTaskId,
        avid: 'ABC-1',
        action: 'add',
        job_type: 'scrape',
        state: 'queued',
        stage: null,
        version: 1,
        updated_at: 1,
      },
    })
  }
  if (config.url === `/resource/jobs/${submitTaskId}` && config.method === 'get') {
    const snapshot = {
      task_id: submitTaskId,
      avid: 'ABC-1',
      action: 'add',
      job_type: 'scrape',
      state: remoteState,
      stage: remoteState === 'running' ? remoteStage || 'source_lookup' : null,
      message: remoteState === 'failed' ? '访问被拒绝' : null,
      version: remoteVersion,
      updated_at: remoteVersion,
    }
    if (holdNextSnapshot) {
      holdNextSnapshot = false
      await new Promise((resolve) => {
        releaseSnapshot = resolve
      })
    }
    return response(config, 200, snapshot)
  }
  throw new Error(`Unexpected API call: ${config.method} ${config.url}`)
}

function response(config, status, data) {
  return {
    config,
    status,
    statusText: 'OK',
    headers: {},
    data: { code: status, message: 'success', data },
  }
}

function storage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }
}

const { useResourceStore } = await import('../src/stores/resource.js')
const { useToastStore } = await import('../src/stores/toast.js')

test('202 remains queued until a terminal snapshot; older events cannot regress it', async () => {
  globalThis.localStorage = storage()
  setActivePinia(createPinia())
  calls.length = 0
  remoteState = 'queued'
  remoteVersion = 1
  const store = useResourceStore()
  const toasts = []
  useToastStore().success = (message) => toasts.push(message)
  try {
    const submitted = await store.addResource('ABC-1')
    assert.equal(submitted.code, 202)
    assert.equal(store.getScrapeJobForAvid('ABC-1').state, 'queued')
    assert.deepEqual(toasts, [])
    assert.equal(calls[0].url, '/resource/jobs')
    await store.refreshPendingScrapeJobs()
    assert.equal(calls.find((call) => call.url === '/resource/jobs/job-1').token, 'signed-token')
    remoteState = 'succeeded'
    remoteVersion = 3
    await store.refreshScrapeJob('job-1')
    assert.equal(store.getScrapeJobForAvid('ABC-1').state, 'succeeded')
    assert.equal(toasts.length, 1)
    store.handleScrapeJobEvent({ job_type: 'scrape', task_id: 'job-1', version: 2 })
    assert.equal(store.getScrapeJobForAvid('ABC-1').state, 'succeeded')
    assert.equal(toasts.length, 1)
  } finally {
    store.stopScrapeTracking()
  }
})

test('page restore fetches terminal snapshot and batch registration stays item-specific', async () => {
  globalThis.localStorage = storage()
  setActivePinia(createPinia())
  const store = useResourceStore()
  remoteState = 'succeeded'
  remoteVersion = 5
  localStorage.setItem(
    'nassav:scrape-jobs:v1',
    JSON.stringify([
      {
        task_id: 'job-1',
        avid: 'ABC-1',
        action: 'add',
        job_type: 'scrape',
        state: 'running',
        stage: 'source_lookup',
        version: 2,
        updated_at: 2,
        status_token: 'signed-token',
      },
    ])
  )
  try {
    store.restoreScrapeJobs()
    await store.refreshPendingScrapeJobs()
    assert.equal(store.getScrapeJobForAvid('ABC-1').state, 'succeeded')
    store.registerScrapeBatch([
      { code: 202, task_id: 'job-2', avid: 'ABC-2', action: 'add', status_token: 'token-2' },
      { code: 404, avid: 'ABC-3', action: 'add' },
    ])
    assert.equal(store.getScrapeJobForAvid('ABC-2').state, 'queued')
    assert.equal(store.getScrapeJobForAvid('ABC-3'), undefined)
  } finally {
    store.stopScrapeTracking()
  }
})

test('monotonic snapshot merge keeps terminal and rejects older versions', () => {
  const terminal = { task_id: 'x', state: 'succeeded', version: 4, updated_at: 4 }
  assert.equal(mergeScrapeJob(terminal, { task_id: 'x', state: 'running', version: 5 }), terminal)
  const current = { task_id: 'y', state: 'running', version: 3, updated_at: 3 }
  assert.equal(mergeScrapeJob(current, { task_id: 'y', state: 'queued', version: 2 }), current)
})

test('WebSocket state changes toast once; stage updates stay quiet and retry is a new job', async () => {
  globalThis.localStorage = storage()
  setActivePinia(createPinia())
  calls.length = 0
  submitTaskId = 'job-1'
  remoteState = 'queued'
  remoteVersion = 1
  remoteStage = null
  const store = useResourceStore()
  const messages = []
  const toast = useToastStore()
  toast.info = (message) => messages.push(['info', message])
  toast.success = (message) => messages.push(['success', message])
  toast.error = (message) => messages.push(['error', message])
  try {
    await store.addResource('ABC-1')
    await new Promise(setImmediate)
    assert.deepEqual(messages, [['info', 'ABC-1 添加任务已排队']])

    remoteState = 'running'
    remoteVersion = 2
    await store.handleScrapeJobEvent({
      job_type: 'scrape',
      task_id: 'job-1',
      state: 'running',
      version: 2,
    })
    assert.deepEqual(messages.at(-1), ['info', 'ABC-1 正在添加'])
    const requestsAfterRunning = calls.length

    remoteVersion = 3
    remoteStage = 'metadata'
    await store.handleScrapeJobEvent({
      job_type: 'scrape',
      task_id: 'job-1',
      state: 'running',
      version: 3,
    })
    assert.equal(calls.length, requestsAfterRunning)
    await store.refreshScrapeJob('job-1')
    assert.equal(store.getScrapeJobForAvid('ABC-1').stage, 'metadata')
    assert.equal(messages.length, 2)

    remoteState = 'failed'
    remoteVersion = 4
    await store.handleScrapeJobEvent({
      job_type: 'scrape',
      task_id: 'job-1',
      state: 'failed',
      version: 4,
    })
    assert.deepEqual(messages.at(-1), ['error', 'ABC-1 访问被拒绝'])
    const requestsAfterFailure = calls.length
    await store.handleScrapeJobEvent({
      job_type: 'scrape',
      task_id: 'job-1',
      state: 'failed',
      version: 4,
    })
    assert.equal(calls.length, requestsAfterFailure)
    assert.equal(messages.length, 3)

    submitTaskId = 'job-2'
    remoteState = 'queued'
    remoteVersion = 1
    await store.addResource('ABC-1')
    await new Promise(setImmediate)
    assert.deepEqual(messages.at(-1), ['info', 'ABC-1 重试任务已排队'])
    assert.equal(messages.length, 4)
  } finally {
    store.dismissScrapeJob('job-2')
    store.stopScrapeTracking()
  }
})

test('WebSocket terminal event during an in-flight snapshot is followed up', async () => {
  globalThis.localStorage = storage()
  setActivePinia(createPinia())
  calls.length = 0
  submitTaskId = 'job-1'
  remoteState = 'queued'
  remoteVersion = 1
  holdNextSnapshot = true
  const store = useResourceStore()
  const success = []
  useToastStore().success = (message) => success.push(message)
  try {
    await store.addResource('ABC-1')
    await new Promise(setImmediate)
    assert.equal(typeof releaseSnapshot, 'function')
    remoteState = 'succeeded'
    remoteVersion = 2
    store.handleScrapeJobEvent({
      job_type: 'scrape',
      task_id: 'job-1',
      state: 'succeeded',
      version: 2,
    })
    releaseSnapshot()
    await new Promise(setImmediate)
    await new Promise(setImmediate)
    assert.equal(store.getScrapeJobForAvid('ABC-1').state, 'succeeded')
    assert.deepEqual(success, ['ABC-1 添加成功'])
    assert.equal(calls.filter((call) => call.url === '/resource/jobs/job-1').length, 2)
  } finally {
    if (releaseSnapshot) releaseSnapshot()
    releaseSnapshot = null
    holdNextSnapshot = false
    store.stopScrapeTracking()
  }
})

test('dismissed in-flight job cannot be restored by its delayed snapshot', async () => {
  globalThis.localStorage = storage()
  setActivePinia(createPinia())
  submitTaskId = 'job-1'
  remoteState = 'running'
  remoteVersion = 2
  holdNextSnapshot = true
  const store = useResourceStore()
  try {
    await store.addResource('ABC-1')
    await new Promise(setImmediate)
    store.dismissScrapeJob('job-1')
    releaseSnapshot()
    await new Promise(setImmediate)
    assert.equal(store.visibleScrapeJobs.length, 0)
    assert.deepEqual(JSON.parse(localStorage.getItem('nassav:scrape-jobs:v1')), [])
  } finally {
    releaseSnapshot?.()
    releaseSnapshot = null
    holdNextSnapshot = false
    store.stopScrapeTracking()
  }
})

test('translation polling and terminal result cannot regress after scrape succeeds', async () => {
  const { scrapeJobNeedsPolling } = await import('../src/stores/scrapeJobState.js')
  const current = {
    task_id: 'parent',
    state: 'succeeded',
    version: 7,
    translation: { task_id: 'child', state: 'completed' },
  }
  assert.equal(scrapeJobNeedsPolling(current), false)
  assert.equal(scrapeJobNeedsPolling({ ...current, translation: { state: 'queued' } }), true)
  assert.equal(scrapeJobNeedsPolling({ ...current, translation: { state: 'unknown' } }), true)
  assert.equal(
    mergeScrapeJob(current, { ...current, translation: { task_id: 'child', state: 'queued' } })
      .translation.state,
    'completed'
  )
})
