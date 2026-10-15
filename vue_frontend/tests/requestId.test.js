import test from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { createRequestId } from '../src/shared/lib/requestId.js'

test('secure context uses native UUID and insecure context uses cryptographic v4 bytes', () => {
  assert.equal(createRequestId({ randomUUID: () => 'native-id' }), 'native-id')
  const fallback = { getRandomValues: (values) => webcrypto.getRandomValues(values) }
  const ids = Array.from({ length: 200 }, () => createRequestId(fallback))
  assert.equal(new Set(ids).size, 200)
  assert.ok(
    ids.every((id) =>
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)
    )
  )
  assert.equal(
    createRequestId({ getRandomValues: (values) => values.fill(255) }),
    'ffffffff-ffff-4fff-bfff-ffffffffffff'
  )
})

test('missing secure entropy fails rather than issuing predictable command IDs', () => {
  assert.throws(() => createRequestId(null), /缺少安全随机数/)
  assert.throws(() => createRequestId({}), /缺少安全随机数/)
})
