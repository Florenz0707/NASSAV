import { onScopeDispose, ref, watch } from 'vue'

export function useRecommendationElapsed(loading) {
  const elapsed = ref(0)
  let started = null,
    timer = null
  const update = () => {
    if (started !== null) elapsed.value = Math.floor((performance.now() - started) / 1000)
  }
  const stop = () => {
    clearInterval(timer)
    timer = null
  }
  watch(
    loading,
    (busy) => {
      stop()
      if (busy) {
        started = performance.now()
        elapsed.value = 0
        timer = setInterval(update, 250)
      } else {
        update()
        started = null
      }
    },
    { flush: 'sync' }
  )
  onScopeDispose(stop)
  return elapsed
}
