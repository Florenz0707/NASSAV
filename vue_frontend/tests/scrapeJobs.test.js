import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { mergeScrapeJob } from '../src/stores/scrapeJobState.js'

const calls = []
let remoteState = 'queued'
let remoteVersion = 1
axios.defaults.adapter = async (config) => {
  calls.push({
    url: config.url,
    method: config.method,
    token: config.headers?.['X-Resource-Job-Token'],
  })
  if (config.url === '/resource/jobs' && config.method === 'post') {
    return response(config, 202, {
      task_id: 'job-1',
      status_token: 'signed-token',
      job: {
        task_id: 'job-1',
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
  if (config.url === '/resource/jobs/job-1' && config.method === 'get') {
    return response(config, 200, {
      task_id: 'job-1',
      avid: 'ABC-1',
      action: 'add',
      job_type: 'scrape',
      state: remoteState,
      stage: remoteState === 'running' ? 'source_lookup' : null,
      version: remoteVersion,
      updated_at: remoteVersion,
    })
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
