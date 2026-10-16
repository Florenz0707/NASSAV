import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { useUserOperationsStore } from '../src/features/tasks/stores/userOperations.js'
import { useToastStore } from '../src/shared/stores/toast.js'
import { buildOperationDetails } from '../src/features/tasks/lib/operationDetails.js'

const snapshot = (changes = {}) => ({
  operation_id: 'refresh-one',
  avid: 'AV-1',
  kind: 'scrape',
  action: 'refresh',
  version: 1,
  state: 'queued',
  stage: 'queued',
  ...changes,
})
test('submitted operations toast once; historical loads, stale snapshots and stage updates stay quiet', () => {
  setActivePinia(createPinia())
  const operations = useUserOperationsStore(),
    toast = useToastStore()
  operations.apply(snapshot({ operation_id: 'history', state: 'failed' }))
  assert.equal(toast.toasts.length, 0)
  operations.apply(snapshot(), { submitted: true })
  assert.equal(toast.toasts.length, 1)
  assert.match(toast.toasts[0].message, /AV-1.*刷新.*已排队/)
  operations.apply(snapshot(), { submitted: true })
  assert.equal(toast.toasts.length, 1)
  operations.apply(snapshot({ version: 2, state: 'running', stage: 'source' }))
  const count = toast.toasts.length
  operations.apply(snapshot({ version: 3, state: 'running', stage: 'cover' }))
  assert.equal(toast.toasts.length, count)
  operations.apply(snapshot({ version: 4, state: 'failed', message: '来源不可用' }))
  assert.equal(toast.toasts.at(-1).type, 'error')
  assert.match(toast.toasts.at(-1).message, /来源不可用/)
  operations.apply(snapshot({ version: 2, state: 'running' }))
  assert.equal(toast.toasts.at(-1).type, 'error')
})
test('shared timeline localizes lifecycle and source phases without leaking unknown stage codes', () => {
  const stages = [
    'queued',
    'running',
    'source_complete',
    'translating',
    'validating',
    'resuming',
    'future_stage',
    'cancelled',
  ]
  const [detail] = buildOperationDetails([
    snapshot({ timeline: stages.map((stage) => ({ stage, state: 'running', at: 10 })) }),
  ])
  assert.deepEqual(
    detail.timeline.map((event) => event.label),
    [
      '任务已排队',
      '开始刮削',
      '来源已获取',
      '正在翻译',
      '校验视频',
      '正在恢复',
      '正在处理',
      '已取消',
    ]
  )
  assert.equal(detail.timeline[0].at, 10)
})

test('a poll arriving before the submit response still produces one notice using the latest state', () => {
  setActivePinia(createPinia())
  const operations = useUserOperationsStore(),
    toast = useToastStore()
  operations.apply(snapshot({ version: 2, state: 'running' }))
  assert.equal(toast.toasts.length, 0)
  operations.apply(snapshot(), { submitted: true })
  assert.equal(toast.toasts.length, 1)
  assert.match(toast.toasts[0].message, /正在执行/)
  assert.equal(operations.visible[0].version, 2)
  operations.apply(snapshot(), { submitted: true })
  assert.equal(toast.toasts.length, 1)
})
