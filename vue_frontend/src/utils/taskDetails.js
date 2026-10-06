import { resolveResourceTitle } from './resourceTitle.js'
import { scrapeWorkflowStatus, SCRAPE_STAGE_LABELS } from '../stores/scrapeJobState.js'

export const isFinishedTask = (task) => ['succeeded', 'failed', 'cancelled'].includes(task.state)
export const TASK_STAGE_LABELS = {
  ...SCRAPE_STAGE_LABELS,
  video_download: '下载视频',
  video_merge: '合并视频',
  video_verify: '校验视频',
  resource_save: '保存资源',
  waiting_slot: '等待下载槽位',
  resume_validation: '校验暂停产物',
  source: '查询来源',
  source_done: '来源已获取',
  source_complete: '来源已获取',
  metadata_complete: '元数据已获取',
  cover_complete: '封面已获取',
  saved: '资源已保存',
  translation_not_requested: '无需翻译',
  translation_superseded: '翻译已被替代',
  metadata_done: '元数据已获取',
  cover_done: '封面已获取',
  avatars: '获取演员头像',
  avatars_done: '头像已获取',
  resource_committed: '资源已保存',
  downloading: '下载中',
  merging: '合并视频',
  video_committed: '视频已保存',
  paused: '已暂停',
  pausing: '请求暂停',
  cancelling: '请求终止',
  cancelled: '已终止',
  succeeded: '已完成',
  failed: '失败',
}
const timelineLabels = {
  queued: '任务已排队',
  running: '开始刮削',
  failed: '刮削失败',
  ...SCRAPE_STAGE_LABELS,
}

function scrapeTimeline(task, workflow) {
  const events = (task.timeline || []).map((event) => ({
    ...event,
    label: timelineLabels[event.stage] || event.stage,
  }))
  if (!events.length) {
    events.push({
      label:
        (task.state === 'failed'
          ? '刮削失败'
          : task.state === 'succeeded'
            ? '资源已保存'
            : timelineLabels[task.stage] || timelineLabels[task.state]) || '状态未知',
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
      label: timelineLabels[workflow.stage] || '翻译状态未知',
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
      taskType: task.task_type || 'download',
      avid: task.avid,
      ...resourceFields(task, 'download'),
      state: task.state ? downloadStates[task.state] || 'unknown' : fallbackState,
      percent,
      speed: task.progress?.speed,
      downloaded: task.progress?.downloaded,
      total: task.progress?.total,
      error: task.error || '',
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
    updated: taskTime(task.updated_at),
    timeline: (task.timeline || []).map((event) => ({
      ...event,
      label:
        event.stage === 'running'
          ? task.job_type === 'download'
            ? '开始下载'
            : '开始刮削'
          : TASK_STAGE_LABELS[event.stage] || timelineLabels[event.stage] || event.stage,
    })),
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
          updated: taskTime(task.updated_at),
        }
      }),
  ]
}
