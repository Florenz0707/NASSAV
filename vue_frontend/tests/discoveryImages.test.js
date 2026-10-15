import test from 'node:test'
import assert from 'node:assert/strict'
import { recommendationApi } from '../src/api/recommendations.js'

test('scoped discovery cards require an owned-result handle and never fall back to arbitrary URLs', () => {
  const item = { cover_url: 'https://private.example/cover.jpg?secret=url', source: 'missav' }
  assert.equal(recommendationApi.getResultCoverUrl(item, true), '')
  const scoped = recommendationApi.getResultCoverUrl(
    { ...item, cover_handle: 'signed:owned-result/value' },
    true
  )
  assert.equal(scoped, '/nassav/api/recommendations/cover?handle=signed%3Aowned-result%2Fvalue')
  assert.ok(!scoped.includes('private.example') && !scoped.includes('secret'))
  assert.match(recommendationApi.getResultCoverUrl(item, false), /source=missav$/)
  assert.equal(recommendationApi.getResultCoverUrl(null, true), '')
})
