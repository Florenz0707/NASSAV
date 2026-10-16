import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'
import { scrapeWorkflowStatus } from '../stores/scrapeJobState.js'

export const isFinishedTask = (task) => ['succeeded', 'failed', 'cancelled'].includes(task.state)
export { TASK_STAGE_LABELS } from './taskTimeline.js'
import { buildTaskTimeline, taskTimelineLabel } from './taskTimeline.js'

function scrapeTimeline(task, workflow) {
  const events = buildTaskTimeline(task.timeline)
  if (!events.length) {
    events.push({
      label:
        (task.state === 'failed'
          ? '刮削失败'
          : task.state === 'succeeded'
            ? '资源已保存'
            : taskTimelineLabel(task.stage, { state: task.state })) || '状态未知',
      at: task.updated_at,
      state: task.state,
    })
  }
  if (
    workflow.stage?.startsWith('translation_') &&
    !events.some((event) => event.stage === workflow.stage)
  )
    events.push({
      stage: workflow.stage,
      label: taskTimelineLabel(workflow.stage),
      at: task.translation?.completed_at,
      state: workflow.state,
    })
  return events
}

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
  active = [],
  pending = [],
  scrapeJobs = [],
  jobs = [],
  resources,
  metadataCache,
  preferredTitle,
  coverUrlFor,
  resolveCoverUrl = (url) => url,
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
      coverUrl: resolveCoverUrl(
        resource.thumbnail_url || resource.cover_url || (hasResource ? coverUrlFor(task.avid) : '')
      ),
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
      taskType: task.task_type || 'download',
      avid: task.avid,
      ...resourceFields(task, 'download'),
      state: task.state ? downloadStates[task.state] || 'unknown' : fallbackState,
      percent,
      speed: task.progress?.speed,
      downloaded: task.progress?.downloaded,
      total: task.progress?.total,
      error: task.error || '',
      createdAt: task.created_at || task.time_start,
      updatedAt: task.updated_at || task.progress?.updated_at || task.time_start || task.created_at,
      updated: taskTime(task.updated_at || task.time_start || task.created_at),
      timeline: [
        ...(task.created_at ? [{ label: '任务已排队', at: task.created_at }] : []),
        ...(task.time_start ? [{ label: '开始下载', at: task.time_start }] : []),
        {
          label:
            task.state === 'FAILURE'
              ? '下载失败'
              : task.state === 'SUCCESS'
                ? '下载完成'
                : '当前下载状态',
          at: task.updated_at || task.progress?.updated_at,
        },
      ],
    }
  }
  const persistent = jobs.map((task) => ({
    id: `${task.job_type}:${task.job_id}`,
    jobId: task.job_id,
    taskId: task.task_id,
    type: task.job_type,
    avid: task.avid,
    action: task.action,
    ...resourceFields(task, task.job_type),
    hasResource: Boolean(task.resource_avid || task.resource_saved),
    coverUrl: task.resource_avid || task.resource_saved ? coverUrlFor(task.avid) : '',
    state: task.state,
    stage: task.stage,
    version: task.version,
    allowedActions: task.allowed_actions || [],
    cleanupState: task.cleanup_state,
    cleanupMessage: task.cleanup_message,
    errorCode: task.error_code,
    percent: Number.isFinite(task.progress?.percent) ? task.progress.percent : null,
    speed: task.progress?.speed,
    downloaded: task.progress?.downloaded,
    total: task.progress?.total,
    translation: task.translation,
    error: task.message || '',
    createdAt: task.created_at,
    updatedAt: task.updated_at,
    updated: taskTime(task.updated_at),
    timeline: buildTaskTimeline(task.timeline, { type: task.job_type }),
  }))
  const legacy = (task, type) =>
    !task.job_id &&
    !jobs.some(
      (job) =>
        job.task_id === task.task_id ||
        (type === 'download' &&
          job.job_type === 'download' &&
          job.avid === task.avid &&
          !isFinishedTask(job))
    )
  return [
    ...persistent,
    ...active.filter((task) => legacy(task, 'download')).map((task) => download(task, 'running')),
    ...pending.filter((task) => legacy(task, 'download')).map((task) => download(task, 'queued')),
    ...scrapeJobs
      .filter((task) => legacy(task, 'scrape'))
      .map((task) => {
        const workflow = scrapeWorkflowStatus(task)
        return {
          id: `scrape:${task.task_id}`,
          taskId: task.task_id,
          type: 'scrape',
          taskType: 'scrape',
          avid: task.avid,
          ...resourceFields(task, 'scrape'),
          state: workflow.state,
          action: task.action,
          stage: workflow.stage,
          timeline: scrapeTimeline(task, workflow),
          translation: task.translation,
          error:
            task.state === 'failed'
              ? task.message || '刮削失败'
              : task.translation?.state === 'failed'
                ? task.translation.message || '资源已保存，但标题翻译失败'
                : '',
          createdAt: task.created_at,
          updatedAt: task.updated_at,
          updated: taskTime(task.updated_at),
        }
      }),
  ]
}

export function resolveTaskFocus(tasks, query) {
  if (typeof query !== 'string' || !query) return ''
  return tasks.find((task) => task.jobId === query || task.taskId === query)?.id || ''
}

export function sortTaskDetails(tasks, ordering) {
  const field = ordering === '-updated_at' ? 'updatedAt' : 'createdAt'
  const timestamp = (value) => {
    const time = new Date(typeof value === 'number' ? value * 1000 : value).getTime()
    return Number.isFinite(time) ? time : 0
  }
  return [...tasks].sort(
    (a, b) => timestamp(b[field]) - timestamp(a[field]) || a.id.localeCompare(b.id)
  )
}
