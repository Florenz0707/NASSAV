import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { resourceApi } from '../src/api/index.js'
import { useResourceStore } from '../src/features/resources/stores/resource.js'

test('batch delete removes only confirmed successes and retains missing results', async () => {
  setActivePinia(createPinia())
  const store = useResourceStore()
  store.resources = [{ avid: 'GOOD-1' }, { avid: 'BAD-1' }, { avid: 'MISSING-1' }]
  const originalBatch = resourceApi.batch
  resourceApi.batch = async () => ({
    data: {
      results: [
        { action: 'delete-all', avid: 'GOOD-1', code: 200 },
        { action: 'delete-all', avid: 'BAD-1', code: 500 },
      ],
    },
  })
  try {
    const result = await store.batchDelete(['GOOD-1', 'BAD-1', 'MISSING-1'])
    assert.deepEqual(
      result.succeeded.map((item) => item.avid),
      ['GOOD-1']
    )
    assert.deepEqual(
      result.failed.map((item) => item.avid),
      ['BAD-1', 'MISSING-1']
    )
    assert.deepEqual(
      store.resources.map((item) => item.avid),
      ['BAD-1', 'MISSING-1']
    )
  } finally {
    resourceApi.batch = originalBatch
  }
})
