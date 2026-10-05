export const TERMINAL_JOB_STATES = new Set(['succeeded', 'failed'])

export const SCRAPE_STAGE_LABELS = {
  source_lookup: '查找资源',
  metadata: '获取元数据',
  cover: '下载封面',
  saving: '保存',
  translation_queued: '提交翻译',
}

export function scrapeJobLabel(job) {
  if (job.state === 'queued') return '已排队'
  if (job.state === 'succeeded') return '已完成'
  if (job.state === 'failed') return '失败'
  return SCRAPE_STAGE_LABELS[job.stage] || '正在处理'
}

export function mergeScrapeJob(current, incoming) {
  if (!current || current.task_id !== incoming.task_id) return incoming
  if (TERMINAL_JOB_STATES.has(current.state) && !TERMINAL_JOB_STATES.has(incoming.state)) {
    return current
  }
  if ((incoming.version || 0) < (current.version || 0)) return current
  if (
    (incoming.version || 0) === (current.version || 0) &&
    (incoming.updated_at || 0) < (current.updated_at || 0)
  ) {
    return current
  }
  return { ...current, ...incoming }
}
