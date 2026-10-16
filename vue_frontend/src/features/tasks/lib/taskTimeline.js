import { SCRAPE_STAGE_LABELS } from '../stores/scrapeJobState.js'

export const TASK_STAGE_LABELS = {
  ...SCRAPE_STAGE_LABELS,
  queued: '任务已排队',
  translating: '正在翻译',
  validating: '校验视频',
  resuming: '正在恢复',
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

// Display policy only: preserve raw stages, event order and server timestamps.
export function taskTimelineLabel(stage, { type = 'scrape', personal = false, state } = {}) {
  if (stage === 'running') return type === 'download' ? '开始下载' : '开始刮削'
  if (stage === 'cancelled' && personal) return '本人请求已撤销'
  return TASK_STAGE_LABELS[stage] || TASK_STAGE_LABELS[state] || '正在处理'
}

export function buildTaskTimeline(events = [], options = {}) {
  return events.map((event) => ({
    ...event,
    label: taskTimelineLabel(event.stage, { ...options, state: event.state }),
  }))
}
