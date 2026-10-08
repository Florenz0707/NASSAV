import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, ref } from 'vue'
import { useRecommendationElapsed } from '../src/features/recommendations/composables/useRecommendationElapsed.js'

test('local elapsed time advances without progress, freezes at completion, resets per request and stops on disposal', (t) => {
  let clock = 0
  t.mock.method(performance, 'now', () => clock)
  t.mock.timers.enable({ apis: ['setInterval'] })
  const loading = ref(false),
    scope = effectScope()
  const elapsed = scope.run(() => useRecommendationElapsed(loading))
  loading.value = true
  clock = 3250
  t.mock.timers.tick(250)
  assert.equal(elapsed.value, 3)
  clock = 4500
  loading.value = false
  assert.equal(elapsed.value, 4)
  clock = 9000
  t.mock.timers.tick(2000)
  assert.equal(elapsed.value, 4)
  loading.value = true
  assert.equal(elapsed.value, 0)
  clock = 10500
  t.mock.timers.tick(250)
  assert.equal(elapsed.value, 1)
  scope.stop()
  clock = 18000
  t.mock.timers.tick(3000)
  assert.equal(elapsed.value, 1)
})
