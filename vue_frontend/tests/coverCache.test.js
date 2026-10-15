import test from 'node:test'
import assert from 'node:assert/strict'
import { resourceApi } from '../src/api/resources.js'

const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

test('cover URLs are shared within the current cache, bounded and revoked on owner reset', async () => {
  const original = resourceApi.fetchCoverBlob,
    max = resourceApi._maxCoverCache
  resourceApi.resetCoverCache()
  resourceApi.fetchCoverBlob = async () => new Blob(['image'])
  resourceApi._maxCoverCache = 1
  try {
    const url = await resourceApi.getCoverObjectUrl('A-1')
    assert.ok(url.startsWith('blob:'))
    assert.equal(await resourceApi.getCoverObjectUrl('A-1'), url)
    await resourceApi.getCoverObjectUrl('B-1')
    assert.equal(resourceApi._coverCache.has('A-1'), false)
    await assert.rejects(fetch(url))
    const current = resourceApi._coverCache.get('B-1')
    resourceApi.resetCoverCache()
    assert.equal(resourceApi._coverCache.size, 0)
    await assert.rejects(fetch(current))
  } finally {
    resourceApi.fetchCoverBlob = original
    resourceApi._maxCoverCache = max
    resourceApi.resetCoverCache()
  }
})

test('old owner response, failure fallback and explicitly revoked pending images cannot repopulate a cache', async () => {
  const original = resourceApi.fetchCoverBlob
  try {
    for (const failure of [false, true]) {
      resourceApi.resetCoverCache()
      const pending = deferred()
      resourceApi.fetchCoverBlob = () => pending.promise
      const old = resourceApi.getCoverObjectUrl('A-1')
      resourceApi.resetCoverCache()
      if (failure) pending.reject(new Error('old request'))
      else pending.resolve(new Blob(['old private cover']))
      assert.equal(await old, null)
      assert.equal(resourceApi._coverCache.size, 0)
    }
    const pending = deferred()
    resourceApi.fetchCoverBlob = () => pending.promise
    const old = resourceApi.getCoverObjectUrl('A-1')
    resourceApi.revokeCoverObjectUrl('A-1')
    pending.resolve(new Blob(['old version']))
    assert.equal(await old, null)
  } finally {
    resourceApi.fetchCoverBlob = original
    resourceApi.resetCoverCache()
  }
})

test('simultaneous image completions reuse one object URL rather than leaking an overwritten URL', async () => {
  const original = resourceApi.fetchCoverBlob
  resourceApi.resetCoverCache()
  resourceApi.fetchCoverBlob = async () => new Blob(['image'])
  try {
    const urls = await Promise.all([
      resourceApi.getCoverObjectUrl('A-1'),
      resourceApi.getCoverObjectUrl('A-1'),
    ])
    assert.equal(urls[0], urls[1])
    assert.equal(resourceApi._coverCache.size, 1)
  } finally {
    resourceApi.fetchCoverBlob = original
    resourceApi.resetCoverCache()
  }
})
