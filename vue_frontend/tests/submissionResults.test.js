import { test } from 'node:test'
import assert from 'node:assert/strict'
import { summarizeSubmissionJobs } from '../src/features/resources/lib/submissionResults.js'
test('batch results follow stable jobs across translation handoff and resume', () => {
  const accepted = [
    { avid: 'A', job_id: 'job-a', task_id: 'old' },
    { avid: 'B', task_id: 'legacy' },
    { avid: 'C', job_id: 'job-c' },
  ]
  const jobs = [
    { avid: 'A', job_id: 'job-a', task_id: 'child', state: 'succeeded' },
    { avid: 'B', task_id: 'legacy', state: 'succeeded', workflow_state: 'running' },
    { avid: 'C', job_id: 'job-c', state: 'cancelled' },
  ]
  const result = summarizeSubmissionJobs(accepted, jobs, [{ avid: 'D', code: 400 }])
  assert.deepEqual(result.success, ['A'])
  assert.deepEqual(result.queued, ['B'])
  assert.deepEqual(
    result.failed.map((item) => item.avid),
    ['D', 'C']
  )
})
