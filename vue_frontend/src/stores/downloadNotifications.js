import { useNotificationsStore } from './notifications.js'
import { useDownloadQueueStore } from './downloadQueue.js'
import { useSettingsStore } from './settings.js'
import { resolveResourceTitle } from '../utils/resourceTitle.js'

export function recordDownloadNotification(type, data) {
  if (!data?.avid) return
  const queue = useDownloadQueueStore()
  if (!queue.isTracked(data)) return
  const metadata = queue.titleCache.get(data.avid)?.metadata || data
  const title = resolveResourceTitle(metadata, useSettingsStore().displayTitle) || data.avid
  const failed = type === 'task_failed'
  useNotificationsStore().record({
    id: `download:${data.task_id || data.avid}:${type}`,
    kind: 'download',
    taskId: data.task_id,
    avid: data.avid,
    title: `${failed ? '下载失败' : '下载完成'} · ${title}`,
    message: data.error || data.message || (failed ? '下载失败，请查看任务信息' : '资源下载已完成'),
    severity: failed ? 'danger' : 'success',
    targetLabel: failed ? '查看任务' : '查看资源',
    target: failed
      ? { path: '/downloads', query: { task: data.task_id, kind: 'download' } }
      : `/resource/${encodeURIComponent(data.avid)}`,
  })
}
