import { useToastStore } from '../../../shared/stores/toast.js'

const actions = { add: '添加', refresh: '刷新', download: '下载' }

// First list hydration is silent; only a submission or known state transition notifies.
export function notifyOperationTransition(previous, item, { submitted = false } = {}) {
  if (!submitted && (!previous || previous.state === item.state)) return
  const toast = useToastStore()
  const action = actions[item.action] || '资源操作'
  const prefix = `${item.avid} ${action}`
  if (item.state === 'queued') toast.info(`${prefix}任务已排队`)
  else if (item.state === 'running') toast.info(`${prefix}任务正在执行`)
  else if (item.state === 'succeeded') toast.success(`${prefix}成功`)
  else if (item.state === 'failed')
    toast.error(`${prefix}失败：${item.message || '请查看任务详情'}`)
  else if (item.state === 'cancelled') toast.info(`${item.avid} 任务已取消`)
}
