import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, nextTick, ref } from 'vue'
import { useRecommendationAdds } from '../src/features/recommendations/composables/useRecommendationAdds.js'

function setup(submit) {
  const scope = effectScope(),
    added = ref(new Set()),
    jobs = ref([]),
    feedback = [],
    errors = []
  const controls = scope.run(() =>
    useRecommendationAdds({
      added,
      jobs: () => jobs.value,
      submit,
      onAdded: (item) => feedback.push(item.avid),
      onError: (error) => errors.push(error.message),
      onExisting: () => {},
    })
  )
  return { ...controls, added, jobs, feedback, errors, stop: () => scope.stop() }
}
const item = { avid: 'REC-001' }
const snapshot = (changes = {}) => ({
  job_id: 'owned',
  avid: item.avid,
  action: 'add',
  state: 'queued',
  version: 1,
  ...changes,
})
const accepted = (job = snapshot()) => ({ data: { job_id: job.job_id, job } })

test('saved resource disables add while translation is still running; terminal event cannot duplicate feedback', async () => {
  const tracker = setup(async () => accepted(snapshot({ state: 'running', resource_saved: true })))
  await tracker.add(item)
  await nextTick()
  assert.equal(tracker.added.value.has(item.avid), true)
  assert.equal(tracker.adding.value.size, 0)
  tracker.jobs.value = [snapshot({ state: 'failed', resource_saved: true, version: 2 })]
  await nextTick()
  await tracker.add(item)
  assert.deepEqual(tracker.feedback, [item.avid])
  tracker.stop()
})

test('accepted job stays busy, ignores another job of same AVID, and releases on failure for retry', async () => {
  let submits = 0
  const tracker = setup(async () => {
    submits++
    return accepted()
  })
  await tracker.add(item)
  await nextTick()
  await tracker.add(item)
  assert.equal(submits, 1)
  tracker.jobs.value = [snapshot({ job_id: 'other', state: 'succeeded' })]
  await nextTick()
  assert.equal(tracker.added.value.size, 0)
  assert.equal(tracker.adding.value.size, 1)
  tracker.jobs.value = [snapshot({ state: 'failed', version: 2 })]
  await nextTick()
  assert.equal(tracker.adding.value.size, 0)
  await tracker.add(item)
  assert.equal(submits, 2)
  tracker.stop()
})

test('success snapshot before submission response is not missed', async () => {
  let resolve
  const tracker = setup(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  const operation = tracker.add(item)
  tracker.jobs.value = [snapshot({ state: 'succeeded', version: 3 })]
  await nextTick()
  resolve(accepted())
  await operation
  await nextTick()
  assert.equal(tracker.added.value.has(item.avid), true)
  tracker.stop()
})

test('409 marks existing, submission failure permits retry, unmounted late response cannot change feedback', async () => {
  const existing = setup(async () => {
    throw { code: 409 }
  })
  await existing.add(item)
  assert.equal(existing.added.value.has(item.avid), true)
  existing.stop()
  const failed = setup(async () => {
    throw new Error('来源不可用')
  })
  await failed.add(item)
  assert.equal(failed.adding.value.size, 0)
  assert.deepEqual(failed.errors, ['来源不可用'])
  failed.stop()
  let resolve
  const tracker = setup(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  const operation = tracker.add(item)
  tracker.stop()
  resolve(accepted(snapshot({ state: 'succeeded' })))
  await operation
  await nextTick()
  assert.deepEqual(tracker.feedback, [])
  assert.equal(tracker.added.value.size, 0)
})

test('shared operation tracking ignores another operation and does not treat CAS conflict as existing', async () => {
  const operation = {
    operation_id: 'owned-operation',
    avid: item.avid,
    action: 'add',
    state: 'queued',
    version: 1,
  }
  const tracker = setup(async () => ({ data: { operation } }))
  await tracker.add(item)
  tracker.jobs.value = [
    { ...operation, operation_id: 'other-operation', state: 'succeeded', version: 2 },
  ]
  await nextTick()
  assert.equal(tracker.added.value.size, 0)
  tracker.jobs.value = [{ ...operation, state: 'succeeded', version: 3 }]
  await nextTick()
  assert.equal(tracker.added.value.has(item.avid), true)
  tracker.stop()
  const conflict = setup(async () => {
    throw { code: 409, sharedLibrary: true, message: 'membership_version_conflict' }
  })
  await conflict.add(item)
  assert.equal(conflict.added.value.size, 0)
  assert.deepEqual(conflict.errors, ['membership_version_conflict'])
  conflict.stop()
  const cancelled = setup(async () => {
    throw { code: 'user_cancelled' }
  })
  await cancelled.add(item)
  assert.equal(cancelled.adding.value.size, 0)
  assert.deepEqual(cancelled.errors, [])
  cancelled.stop()
})
