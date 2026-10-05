import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildTaskDetails } from '../src/utils/taskDetails.js'

const build = (changes = {}) =>
  buildTaskDetails({
    active: [],
    pending: [],
    scrapeJobs: [],
    resources: [],
    metadataCache: new Map(),
    preferredTitle: 'source_title',
    coverUrlFor: (avid) => '/cover/' + avid,
    ...changes,
  })
test('download and scrape protocols preserve identity, title preferences and actual progress', () => {
  const cache = new Map([
    [
      'AV-1',
      {
        metadata: {
          avid: 'AV-1',
          source_title: 'Source',
          translated_title: 'Translated',
          thumbnail_url: '/thumb',
        },
      },
    ],
  ])
  const input = {
    active: [
      {
        task_id: 'one',
        avid: 'AV-1',
        state: 'STARTED',
        progress: { percent: '45.5', speed: '2 MB/s' },
      },
    ],
    pending: [{ task_id: 'two', avid: 'AV-1' }],
    metadataCache: cache,
  }
  const tasks = build(input)
  assert.deepEqual(
    tasks.map((t) => t.state),
    ['running', 'queued']
  )
  assert.notEqual(tasks[0].id, tasks[1].id)
  assert.equal(tasks[0].title, 'Source')
  assert.equal(build({ ...input, preferredTitle: 'translated_title' })[0].title, 'Translated')
  assert.equal(tasks[0].coverUrl, '/thumb')
  assert.equal(tasks[0].percent, 45.5)
  assert.equal(tasks[1].percent, null)
  assert.equal(input.active[0].title, undefined)
})
test('unknown states and absent metadata remain explicit; refresh failures retain resource identity', () => {
  const tasks = build({
    active: [{ avid: 'AV-1', state: 'NEW_STATE', progress: { percent: 'invalid' } }],
    scrapeJobs: [
      { task_id: 'add', avid: 'AV-2', action: 'add', state: 'running', stage: 'metadata' },
      { task_id: 'refresh', avid: 'AV-3', action: 'refresh', state: 'failed', message: '来源超时' },
    ],
  })
  assert.equal(tasks[0].state, 'unknown')
  assert.equal(tasks[0].percent, null)
  assert.equal(tasks[1].title, '')
  assert.equal(tasks[1].coverUrl, '')
  assert.equal(tasks[1].hasResource, false)
  assert.equal(tasks[1].stage, 'metadata')
  assert.equal(tasks[2].hasResource, true)
  assert.equal(tasks[2].error, '来源超时')
  assert.equal(tasks[2].coverUrl, '/cover/AV-3')
})

test('scrape snapshot titles follow preference and translation status is separate from saved resource', () => {
  const input = {
    scrapeJobs: [
      {
        task_id: 'job',
        avid: 'AV-1',
        state: 'succeeded',
        resource: { avid: 'AV-1', source_title: 'Source', translated_title: 'Translation' },
        translation: { task_id: 'child', state: 'failed' },
      },
    ],
    preferredTitle: 'translated_title',
  }
  const task = build(input)[0]
  assert.equal(task.title, 'Translation')
  assert.equal(task.state, 'succeeded')
  assert.equal(task.translation.state, 'failed')
})
