import { resolveResourceTitle } from './resourceTitle.js'

const downloadStates = {
  PENDING: 'queued',
  RECEIVED: 'queued',
  RETRY: 'queued',
  STARTED: 'running',
  PROGRESS: 'running',
  SUCCESS: 'succeeded',
  FAILURE: 'failed',
}
export function taskTime(value) {
  if (!value) return ''
  const date = new Date(typeof value === 'number' ? value * 1000 : value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { hour12: false })
}

// Unify display fields only; queue/job stores retain ownership of raw snapshots.
export function buildTaskDetails({
  active,
  pending,
  scrapeJobs,
  resources,
  metadataCache,
  preferredTitle,
  coverUrlFor,
}) {
  const metadataFor = (task) => ({
    ...resources.find((r) => r.avid === task.avid),
    ...metadataCache?.get(task.avid)?.metadata,
    ...task.resource,
  })
  const resourceFields = (task, type) => {
    const metadata = metadataFor(task)
    const resource = { ...task, ...metadata, avid: task.avid }
    const title = resolveResourceTitle(resource, preferredTitle)
    const hasResource =
      type === 'download' ||
      task.action === 'refresh' ||
      task.state === 'succeeded' ||
      Boolean(metadata.avid)
    return {
      title: title === task.avid ? '' : title,
      hasResource,
      coverUrl:
        resource.thumbnail_url || resource.cover_url || (hasResource ? coverUrlFor(task.avid) : ''),
    }
  }
  const download = (task, fallbackState) => {
    const rawPercent = task.progress?.percent
    const percent =
      rawPercent !== null &&
      rawPercent !== undefined &&
      rawPercent !== '' &&
      Number.isFinite(Number(rawPercent))
        ? Math.min(100, Math.max(0, Number(rawPercent)))
        : null
    return {
      id: `download:${task.task_id || task.avid}`,
      taskId: task.task_id,
      type: 'download',
      avid: task.avid,
      ...resourceFields(task, 'download'),
      state: task.state ? downloadStates[task.state] || 'unknown' : fallbackState,
      percent,
      speed: task.progress?.speed,
      downloaded: task.progress?.downloaded,
      total: task.progress?.total,
      error: task.error || '',
      updated: taskTime(task.updated_at || task.time_start || task.created_at),
    }
  }
  return [
    ...active.map((task) => download(task, 'running')),
    ...pending.map((task) => download(task, 'queued')),
    ...scrapeJobs.map((task) => ({
      id: `scrape:${task.task_id}`,
      taskId: task.task_id,
      type: 'scrape',
      avid: task.avid,
      ...resourceFields(task, 'scrape'),
      state: task.state,
      action: task.action,
      stage: task.stage,
      translation: task.translation,
      error: task.state === 'failed' ? task.message || '刮削失败' : '',
      updated: taskTime(task.updated_at),
    })),
  ]
}
