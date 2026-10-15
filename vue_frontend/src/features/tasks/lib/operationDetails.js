import { TASK_STAGE_LABELS, taskTime } from './taskDetails.js'
import { resolveResourceTitle } from '../../resources/lib/resourceTitle.js'

export function buildOperationDetails(operations, resources = [], preferredTitle) {
  const metadata = new Map(resources.map((item) => [item.avid, item]))
  return operations.map((item) => {
    const resource = metadata.get(item.avid)
    return {
      id: `operation:${item.operation_id}`,
      operationId: item.operation_id,
      type: item.kind,
      action: item.action,
      avid: item.avid,
      title: resource ? resolveResourceTitle(resource, preferredTitle) : '',
      hasResource: Boolean(resource?.membership_state === 'active'),
      coverUrl: resource?.thumbnail_url || resource?.cover_url || '',
      state: item.state,
      stage: item.stage,
      version: item.version,
      allowedActions: item.allowed_actions?.includes('cancel') ? ['cancel'] : [],
      percent: Number.isFinite(item.progress?.percent) ? item.progress.percent : null,
      speed: item.progress?.speed,
      downloaded: item.progress?.downloaded,
      total: item.progress?.total,
      error: item.message || '',
      errorCode: item.error_code,
      createdAt: item.created_at,
      updatedAt: item.updated_at,
      updated: taskTime(item.updated_at),
      timeline: (item.timeline || []).map((event) => ({
        ...event,
        label:
          event.stage === 'cancelled'
            ? '本人请求已撤销'
            : TASK_STAGE_LABELS[event.stage] || event.stage,
      })),
    }
  })
}
