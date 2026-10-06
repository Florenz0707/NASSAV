import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildTaskDetails, isFinishedTask } from '../src/utils/taskDetails.js'

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

test('scrape snapshot titles follow preference and translation failures affect workflow but preserve saved resource identity', () => {
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
  assert.equal(task.state, 'failed')
  assert.equal(task.stage, 'translation_failed')
  assert.equal(task.hasResource, true)
  assert.equal(task.translation.state, 'failed')
})

test('translation remains part of the workflow until its terminal result, and finished includes failures', () => {
  for (const [child, expected, finished] of [
    ['queued', 'running', false],
    ['translating', 'running', false],
    ['unknown', 'running', false],
    ['completed', 'succeeded', true],
    ['failed', 'failed', true],
    ['skipped', 'succeeded', true],
  ]) {
    const raw = {
      task_id: 'parent',
      avid: 'AV-1',
      state: 'succeeded',
      translation: { state: child },
      timeline: [{ stage: 'saving', at: 1700000000 }],
    }
    const task = build({ scrapeJobs: [raw] })[0]
    assert.equal(task.state, expected)
    assert.equal(isFinishedTask(task), finished)
    assert.equal(raw.state, 'succeeded')
    assert.equal(task.timeline[0].label, '保存')
    assert.equal(task.timeline[0].at, 1700000000)
  }
})

test('persistent task state owns parent translation, resume identity and saved-resource link', () => {
  const raw = {
    job_id: 'stable',
    task_id: 'new-attempt',
    job_type: 'scrape',
    avid: 'AV-9',
    state: 'paused',
    stage: 'translation_translating',
    version: 8,
    resource_saved: false,
    resource: { avid: 'AV-9', source_title: '已获取标题' },
    translation: { state: 'paused' },
    allowed_actions: ['resume', 'cancel'],
    cleanup_state: 'not_required',
    timeline: [{ stage: 'paused', at: 1 }],
  }
  const tasks = build({ jobs: [raw], scrapeJobs: [raw] })
  assert.equal(tasks.length, 1)
  assert.equal(tasks[0].id, 'scrape:stable')
  assert.equal(tasks[0].state, 'paused')
  assert.equal(tasks[0].hasResource, false)
  assert.equal(tasks[0].title, '已获取标题')
  assert.equal(tasks[0].timeline[0].label, '已暂停')
  assert.equal(isFinishedTask({ state: 'cancelled' }), true)
})
