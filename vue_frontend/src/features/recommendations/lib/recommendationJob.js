function waitForPoll(signal) {
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    const timer = setTimeout(finish, 1000)
    signal.addEventListener('abort', finish, { once: true })
    if (signal.aborted) finish()
  })
}

// Submission must finish even after local abort, so the returned ID can be cancelled.
export async function runRecommendationJob(
  api,
  parameters,
  { signal, onJob, onSnapshot, wait = waitForPoll }
) {
  const submitted = await api.startJob(parameters)
  const id = submitted.data?.job_id
  if (!id) throw new Error('推荐任务响应无效')
  if (signal.aborted) {
    await api.cancelJob(id)
    return null
  }
  onJob(id)
  let response = submitted
  let version = -1
  while (!signal.aborted) {
    const job = response.data
    if (!Number.isInteger(job?.version)) throw new Error('推荐任务版本无效')
    if (job?.job_id !== id) throw new Error('推荐任务身份不匹配')
    if (Number.isInteger(job.version) && job.version > version) {
      version = job.version
      onSnapshot(job)
      if (job.state === 'succeeded') return { data: job.result }
      if (job.state === 'cancelled') return null
      if (job.state === 'failed') throw new Error(job.message || '推荐失败，请重试')
    }
    await wait(signal)
    if (signal.aborted) return null
    response = await api.getJob(id, { signal })
  }
  return null
}
