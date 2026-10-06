import { resolveResourceTitle } from './resourceTitle.js'
import { scrapeWorkflowStatus, SCRAPE_STAGE_LABELS } from '../stores/scrapeJobState.js'

export const isFinishedTask = (task) => ['succeeded', 'failed'].includes(task.state)
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
  return [
    ...active.map((task) => download(task, 'running')),
    ...pending.map((task) => download(task, 'queued')),
    ...scrapeJobs.map((task) => {
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
