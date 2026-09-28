import { useToastStore } from './toast.js'

export function notifyScrapeJobTransition(previous, job, isRetry) {
  if (previous?.state === job.state) return false
  const toast = useToastStore()
  const action = job.action === 'add' ? '添加' : '刷新'
  if (job.state === 'queued')
    toast.info(`${job.avid} ${isRetry ? '重试任务' : `${action}任务`}已排队`)
  else if (job.state === 'running') toast.info(`${job.avid} 正在${action}`)
  else if (job.state === 'succeeded') toast.success(`${job.avid} ${action}成功`)
  else if (job.state === 'failed') toast.error(`${job.avid} ${job.message || `${action}失败`}`)
  return job.state === 'succeeded'
}

export function notifyScrapeBatch(queued, failed) {
  const toast = useToastStore()
  if (queued) toast.info(`${queued} 个资源任务已排队`)
  if (failed) toast.warning(`${failed} 个资源提交失败`)
}
