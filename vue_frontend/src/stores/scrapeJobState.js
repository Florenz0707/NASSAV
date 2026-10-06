export const TERMINAL_JOB_STATES = new Set(['succeeded', 'failed'])

export const SCRAPE_STAGE_LABELS = {
  source_lookup: '查找资源',
  metadata: '获取元数据',
  cover: '下载封面',
  saving: '保存',
  translation_queued: '提交翻译',
  translation_translating: '正在翻译',
  translation_completed: '翻译完成',
  translation_failed: '翻译失败',
  translation_skipped: '翻译跳过',
  translation_unknown: '翻译状态暂不可用',
  translation_unavailable: '翻译结果未记录或已过期',
  resource_saved: '资源已保存',
}

export function scrapeWorkflowStatus(job) {
  if (job.state !== 'succeeded')
    return { state: job.state, stage: job.state === 'failed' ? 'failed' : job.stage }
  const child = job.translation?.state
  if (['queued', 'translating', 'unknown'].includes(child))
    return { state: 'running', stage: `translation_${child}` }
  if (child === 'failed') return { state: 'failed', stage: 'translation_failed' }
  return {
    state: 'succeeded',
    stage: child && child !== 'not_requested' ? `translation_${child}` : 'resource_saved',
  }
}

export function scrapeJobLabel(job) {
  if (job.state === 'queued') return '已排队'
  if (job.state === 'succeeded')
    return SCRAPE_STAGE_LABELS[scrapeWorkflowStatus(job).stage] || '已完成'
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
  const merged = { ...current, ...incoming }
  if (
    current.translation?.task_id &&
    current.translation.task_id === incoming.translation?.task_id &&
    ['completed', 'failed', 'skipped'].includes(current.translation.state) &&
    ['queued', 'translating', 'unknown'].includes(incoming.translation.state)
  ) {
    merged.translation = current.translation
  }
  return merged
}

export function scrapeJobNeedsPolling(job) {
  return (
    !TERMINAL_JOB_STATES.has(job.state) ||
    (job.state === 'succeeded' &&
      ['queued', 'translating', 'unknown'].includes(job.translation?.state))
  )
}
