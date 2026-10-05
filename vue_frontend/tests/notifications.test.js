import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { useNotificationsStore } from '../src/stores/notifications.js'
import { notifyScrapeJobTransition } from '../src/stores/scrapeJobNotifications.js'
import { recordDownloadNotification } from '../src/stores/downloadNotifications.js'
import { useDownloadQueueStore } from '../src/stores/downloadQueue.js'
import { useToastStore } from '../src/stores/toast.js'

test('session events deduplicate, cap history, keep failure after read and clear on logout', () => {
  setActivePinia(createPinia())
  const store = useNotificationsStore()
  store.record({ id: 'failure', severity: 'danger' })
  store.record({ id: 'failure' })
  assert.equal(store.unreadCount, 1)
  store.markRead('failure')
  assert.equal(store.events[0].severity, 'danger')
  for (let i = 0; i < 110; i++) store.record({ id: String(i) })
  assert.equal(store.events.length, 100)
  store.readAll()
  assert.equal(store.unreadCount, 0)
  store.show()
  store.reset()
  assert.equal(store.opened, false)
  assert.equal(store.events.length, 0)
})
test('scrape and translation outcomes are recorded separately without duplicate snapshots', () => {
  setActivePinia(createPinia())
  const toast = useToastStore()
  toast.success = () => {}
  toast.error = () => {}
  const job = {
    task_id: 'job',
    avid: 'AV-1',
    action: 'add',
    state: 'succeeded',
    resource: { source_title: 'Source' },
    translation: { task_id: 'child', state: 'queued' },
  }
  notifyScrapeJobTransition({ state: 'running' }, job)
  const finished = { ...job, translation: { task_id: 'child', state: 'failed' } }
  notifyScrapeJobTransition(job, finished)
  notifyScrapeJobTransition(job, finished)
  const store = useNotificationsStore()
  assert.equal(store.events.length, 2)
  assert.equal(store.events[0].kind, 'translation')
  assert.equal(store.events[0].severity, 'danger')
  assert.equal(store.events[1].title, '刮削完成 · Source')
})
test('download events use resource names and ignored IDs do not create notifications', () => {
  setActivePinia(createPinia())
  const queue = useDownloadQueueStore()
  queue.titleCache.set('AV-1', { metadata: { source_title: 'Named resource' } })
  recordDownloadNotification('task_completed', { task_id: 'd1', avid: 'AV-1' })
  queue.dismissTasks(['ignored'])
  recordDownloadNotification('task_failed', { task_id: 'ignored', avid: 'AV-1' })
  assert.equal(useNotificationsStore().events.length, 1)
  assert.equal(useNotificationsStore().events[0].title, '下载完成 · Named resource')
})
