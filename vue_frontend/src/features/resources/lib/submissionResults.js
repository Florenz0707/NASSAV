export function summarizeSubmissionJobs(accepted, jobs, submissionFailed = []) {
  const byOperation = new Map(
    jobs.filter((job) => job.operation_id).map((job) => [job.operation_id, job])
  )
  const byJob = new Map(jobs.filter((job) => job.job_id).map((job) => [job.job_id, job]))
  const byAttempt = new Map(jobs.map((job) => [job.task_id, job]))
  const queued = [],
    success = [],
    failed = [...submissionFailed]
  for (const item of accepted) {
    const job = item.operation_id
      ? byOperation.get(item.operation_id) || item.snapshot
      : item.job_id
        ? byJob.get(item.job_id)
        : byAttempt.get(item.task_id)
    const state = job?.workflow_state || job?.state
    if (state === 'succeeded') success.push(item.avid)
    else if (state === 'failed' || state === 'cancelled')
      failed.push({
        avid: item.avid,
        code: job.error_code || state,
        message: job.message || (state === 'cancelled' ? '任务已终止' : '任务失败'),
      })
    else queued.push(item.avid)
  }
  return { queued, success, failed }
}
