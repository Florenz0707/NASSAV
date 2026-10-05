import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { resolveResourceTitle } from '../src/utils/resourceTitle.js'
import { resourceApi } from '../src/api/index.js'
import { useDownloadQueueStore } from '../src/stores/downloadQueue.js'
import { useSettingsStore } from '../src/stores/settings.js'

test('title preference and missing-field fallbacks are consistent for local and external records', () => {
  const metadata = {
    original_title: 'Original',
    source_title: 'Source',
    translated_title: 'Translated',
    avid: 'AV-1',
  }
  assert.equal(resolveResourceTitle(metadata, 'source_title'), 'Source')
  assert.equal(resolveResourceTitle(metadata, 'original_title'), 'Original')
  assert.equal(
    resolveResourceTitle({ ...metadata, original_title: '' }, 'original_title'),
    'Translated'
  )
  assert.equal(resolveResourceTitle({ title: 'External', avid: 'AV-2' }), 'External')
  assert.equal(resolveResourceTitle({ avid: 'AV-3' }), 'AV-3')
  assert.equal(resolveResourceTitle(null), '')
})

test('queue metadata stays raw, updates with title preference and ignores responses after tracking stops', async () => {
  setActivePinia(createPinia())
  const original = resourceApi.getMetadata
  let finish
  resourceApi.getMetadata = () =>
    new Promise((resolve) => {
      finish = resolve
    })
  try {
    const queue = useDownloadQueueStore()
    const settings = useSettingsStore()
    queue.updateTaskData({ active_tasks: [{ avid: 'AV-1' }], active_count: 1 })
    finish({ data: { source_title: 'Source', translated_title: 'Translated' } })
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(queue.activeTasks[0].title, 'Source')
    settings.displayTitle = 'translated_title'
    await nextTick()
    assert.equal(queue.activeTasks[0].title, 'Translated')
    queue.updateTaskData({ active_tasks: [{ avid: 'AV-2' }], active_count: 1 })
    queue.stopTracking()
    finish({ data: { source_title: 'Too late' } })
    await new Promise((resolve) => setImmediate(resolve))
    assert.equal(queue.titleCache.has('AV-2'), false)
    assert.equal(queue.activeTasks[0].title, null)
  } finally {
    resourceApi.getMetadata = original
  }
})
