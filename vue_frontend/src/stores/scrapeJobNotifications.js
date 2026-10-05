import { useNotificationsStore } from './notifications.js'
import { useSettingsStore } from './settings.js'
import { resolveResourceTitle } from '../utils/resourceTitle.js'
import { useToastStore } from './toast.js'

export function notifyScrapeJobTransition(previous, job, isRetry) {
  const notifications = useNotificationsStore()
  const name =
    resolveResourceTitle(job.resource || job, useSettingsStore().displayTitle) || job.avid
  const target = { path: '/downloads', query: { task: job.task_id, kind: 'scrape' } }
  if (['succeeded', 'failed'].includes(job.state) && previous?.state !== job.state) {
    notifications.record({
      id: `scrape:${job.task_id}:${job.state}`,
      kind: 'scrape',
      taskId: job.task_id,
      avid: job.avid,
      title: `${job.state === 'failed' ? '刮削失败' : '刮削完成'} · ${name}`,
      message: job.message || '资源已保存；翻译结果单独跟踪。',
      severity: job.state === 'failed' ? 'danger' : 'success',
      targetLabel: '查看任务',
      target,
    })
  }
  if (
    ['completed', 'failed', 'skipped'].includes(job.translation?.state) &&
    previous?.translation?.state !== job.translation.state
  ) {
    notifications.record({
      id: `translation:${job.task_id}:${job.translation.task_id || 'submission'}:${job.translation.state}`,
      kind: 'translation',
      taskId: job.task_id,
      avid: job.avid,
      title: `${job.translation.state === 'completed' ? '翻译成功' : job.translation.state === 'failed' ? '翻译失败' : '翻译跳过'} · ${name}`,
      message: job.translation.message || '该次任务的翻译结果已确认。',
      severity: job.translation.state === 'failed' ? 'danger' : 'success',
      targetLabel: '查看任务',
      target,
    })
  }
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
